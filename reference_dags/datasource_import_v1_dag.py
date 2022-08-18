from uuid import uuid4
from json import loads as json_loads
from datetime import timedelta, datetime
from airflow import DAG
from airflow.exceptions import AirflowFailException
from airflow.hooks.http_hook import HttpHook
from airflow.models import Variable
from airflow.operators.docker_operator import DockerOperator
from airflow.operators.dummy_operator import DummyOperator
from airflow.operators.python_operator import PythonOperator
from airflow.operators.dagrun_operator import DagRunOrder
from airflow.utils.trigger_rule import TriggerRule
from multiple_trigger_dag_run_operator import MultipleTriggerDagRunOperator
from airflow.contrib.operators.ecs_operator import ECSOperator
import copy
import re

AWS_ENV = Variable.get('aws__env', deserialize_json=True)
# Superset ENV Variables
SUPERSET__ENV = Variable.get('superset__env', deserialize_json=True)
SUPERSET__ENV.update(AWS_ENV)
# Datasource Import ENV Variables
DATASOURCE_IMPORT__ENV = Variable.get('datasource_import__env', deserialize_json=True)
DATASOURCE_IMPORT__ENV.update(AWS_ENV)
# Can be moved to Airflow Variable
DOCKER_VOLUME__DAG = Variable.get('dag_output_path')
# Fixed
DOCKER_VOLUME__SUPERSET = '/app/superset_home'
DOCKER_VOLUME__DATASOURCE_IMPORT = '/app/tmp'

ATHENA_TASK_ENV = Variable.get('athena_task_details', deserialize_json=True)

# Callbacks
def cb_chain(*args):
    """Callback to chain multiple callback executions, provides context"""
    def callback_chained(context):
        for func in args:
            func(context)
    return callback_chained


def cb__json_deserialize(context):
    """Deserialize JSON response"""
    task_id = context['task'].task_id
    task_instance = context['task_instance']
    rv_json_str = task_instance.xcom_pull(task_ids=task_id, key='return_value')
    task_instance.xcom_push(key="return_dict", value=json_loads(rv_json_str))


def cb__httphook_report(context):
    prediction = context['dag_run'].conf['prediction']
    # Task Data
    task_id = context['task'].task_id
    task_state = context['task_instance'].state
    if task_state == 'success':
        if task_id == 'internal.start':
            status = 'STARTED'
        elif task_id == 'internal.end':
            status = 'COMPLETED'
        else:
            status = 'SUCCESS'
    else:
        status = 'FAILURE'
    # HTTP Hook
    payload = {
        'status': status,
        'airflow': {
            'state': task_state,
            'task_id': task_id,
            'execution_date': str(context['task_instance'].execution_date),
            'duration': context['task_instance'].duration
        }
    }
    # Extras
    if 'exception' in context:
        payload['airflow']['error'] = str(context['exception'])
    if status == 'COMPLETED':
        payload['airflow']['url'] = f"/superset/dashboard/{prediction}/"
    # Run HTTP Hook
    core_endpoint = HttpHook(method='PATCH', http_conn_id='core_jobs_endpoint')
    core_endpoint.run(
        f'/core_jobs/api/v1/dashboard-import/{prediction}/status',
        json=payload,
        headers={'Content-Type': 'application/json'}
    )


# DAG definition
default_args = {
    'owner': 'refy-platform',
    'start_date': datetime(2021, 2, 9),
    'depends_on_past': False,
    'provide_context': True,
    'retries': 0
}

dag = DAG(
    'datasource_import_v1_dag',
    description='Datasource Import DAG',
    catchup=False,
    schedule_interval=None,
    default_args=default_args,
    jinja_environment_kwargs={
        'trim_blocks': True,
        'lstrip_blocks': True
    }
)


# Python internal - Get Variables
def internal_start(*args, **kwargs):  # pylint: disable=unused-argument
    required_keys = (
        'prediction',
        'athena__schema_name'
    )
    # Check required conf key
    for conf_key in required_keys:
        if conf_key not in kwargs['dag_run'].conf:
            raise AirflowFailException(f'Missing Airflow conf value: {conf_key}')

    run_guid = uuid4()
    return {
        'run_guid': run_guid,
        'datasource_filename': f'datasource_{run_guid}.yaml',
        'datasource_export_filename': f'datasource_export_{run_guid}.json',
        'dashboard_filename': f'dashboard_{run_guid}.json'
    }


internal__start = PythonOperator(
    dag=dag,
    task_id='internal.start',
    python_callable=internal_start,
    on_success_callback=cb__httphook_report,
    on_failure_callback=cb__httphook_report,
)


# Python internal - Get refy Job Data
def query_job(*args, **kwargs):  # pylint: disable=unused-argument
    job = kwargs['dag_run'].conf['prediction']
    # Query Endpoint
    core_endpoint = HttpHook(method='GET', http_conn_id='core_jobs_endpoint')
    response = core_endpoint.run(
        f'/core_jobs/api/v1/jobs/{job}',
        headers={'Content-Type': 'application/json'}
    )
    client_rv = response.json()
    return {
        'client': client_rv['client'],
        'project': client_rv['project'],
        'prediction': client_rv['id'],
        'title': client_rv['name'].replace('"', '\\"'),
        's3_data_path': client_rv['results']['predictions'],
        'folder_path': '{}/{}/{}'.format(
            client_rv['client'],
            client_rv['project'],
            client_rv['id'],
        )
    }


internal__query_job = PythonOperator(
    dag=dag,
    task_id='internal.query_job',
    python_callable=query_job,
    on_success_callback=cb__httphook_report,
    on_failure_callback=cb__httphook_report
)

# datasource_import__build_datasource = DockerOperator(
#     dag=dag,
#     task_id='datasource_import.build_datasource',
#     image='refy-athena-import',
#     xcom_push=True,
#     volumes=[
#         f'{DOCKER_VOLUME__DAG}:{DOCKER_VOLUME__DATASOURCE_IMPORT}'
#     ],
#     user='dataimp',
#     environment=DATASOURCE_IMPORT__ENV,
#     command=DATASOURCE_IMPORT__BUILD_DATASOURCE,
#     on_success_callback=cb_chain(cb__json_deserialize, cb__httphook_report),
#     on_failure_callback=cb__httphook_report
# )

# Docker datasource_import - Datasource/Athena Import
DATASOURCE_IMPORT__BUILD_DATASOURCE = """
{% set is_rv = ti.xcom_pull(task_ids='internal.start', key='return_value') %}
{% set qj_rv = ti.xcom_pull(task_ids='internal.query_job', key='return_value') %}
process-athena
--application-id refy-athena-import-test
--prediction {{ qj_rv['prediction'] }}
--client-id {{ qj_rv['client'] }}
--athena-schema {{ dag_run.conf['athena__schema_name'] }}
--data-s3-path {{ qj_rv['s3_data_path'] }}
--output-path /app/tmp/{{ qj_rv['folder_path'] }}/{{ is_rv['datasource_filename'] }}
"""
# ECS Args
ecs_operator_args_template = {
    'aws_conn_id': 'aws_default',
    'region_name': AWS_ENV['REGION_NAME'],
    'launch_type': 'FARGATE',
    'cluster': ATHENA_TASK_ENV['AWS_CLUSTER'],
    'task_definition': ATHENA_TASK_ENV['TASK_DEFINITION'],
    'network_configuration': {
        'awsvpcConfiguration': {
            'assignPublicIp': 'ENABLED',
            'subnets': [ATHENA_TASK_ENV['AWS_NETWORK_SUBNET']]
        }
    },
    'awslogs_group': '/ecs/' + ATHENA_TASK_ENV['TASK_DEFINITION'],
    'awslogs_stream_prefix': 'ecs/' + ATHENA_TASK_ENV['AWS_CONTAINER_NAME'],
    'overrides': {
        'containerOverrides': [
            {
                'name': ATHENA_TASK_ENV['AWS_CONTAINER_NAME'],
                'command': [
                    'process-athena',
                    '--application-id',
                    'refy-athena-import-test',
                    '--prediction',
                    "{{ ti.xcom_pull(task_ids='internal.query_job', key='return_value')['prediction'] }}",
                    '--client-id',
                    "{{ ti.xcom_pull(task_ids='internal.query_job', key='return_value')['client'] }}",
                    '--athena-schema',
                    "{{ dag_run.conf['athena__schema_name'] }}",
                    '--data-s3-path',
                    "{{ ti.xcom_pull(task_ids='internal.query_job', key='return_value')['s3_data_path'] }}",
                    '--output-path',
                    "/app/tmp/{{ ti.xcom_pull(task_ids='internal.query_job', key='return_value')['folder_path'] }}/{{ ti.xcom_pull(task_ids='internal.start', key='return_value')['datasource_filename'] }}"
                ]
            },
        ],
    },
}

ecs_operator_args = copy.deepcopy(ecs_operator_args_template)
ecs_datasource_import__build_datasource = ECSOperator(
    task_id='ecs.datasource_import.build_datasource',
    dag=dag,
    retries=3,
    retry_delay=timedelta(seconds=10),
    **ecs_operator_args
)


# Docker superset - Datasources Import
SUPERSET__IMPORT_DATASOURCES = """
{% set is_rv = ti.xcom_pull(task_ids='internal.start', key='return_value') %}
{% set qj_rv = ti.xcom_pull(task_ids='internal.query_job', key='return_value') %}
import-datasources
--path /app/superset_home/{{ qj_rv['folder_path'] }}/{{ is_rv['datasource_filename'] }}
"""
superset__import_datasource = DockerOperator(
    dag=dag,
    task_id='superset.import_datasource',
    image='refy-superset_superset-cli',
    network_mode='host',
    volumes=[
        f'{DOCKER_VOLUME__DAG}:{DOCKER_VOLUME__SUPERSET}'
    ],
    user='superset',
    environment=SUPERSET__ENV,
    command=SUPERSET__IMPORT_DATASOURCES,
    on_success_callback=cb__httphook_report,
    on_failure_callback=cb__httphook_report
)


# Docker superset - Import Datasources
SUPERSET__EXPORT_DATASOURCES = """
{% set is_rv = ti.xcom_pull(task_ids='internal.start', key='return_value') %}
{% set qj_rv = ti.xcom_pull(task_ids='internal.query_job', key='return_value') %}
export-table
--back-references
--table {{ qj_rv['prediction'] }}
--datasource-file /app/superset_home/{{ qj_rv['folder_path'] }}/{{ is_rv['datasource_export_filename'] }}
"""
superset__export_datasource = DockerOperator(
    dag=dag,
    task_id='superset.export_datasource',
    image='refy-superset_superset-cli',
    network_mode='host',
    volumes=[
        f'{DOCKER_VOLUME__DAG}:{DOCKER_VOLUME__SUPERSET}'
    ],
    user='superset',
    environment=SUPERSET__ENV,
    command=SUPERSET__EXPORT_DATASOURCES,
    on_success_callback=cb__httphook_report,
    on_failure_callback=cb__httphook_report
)


# Docker datasource_import - Build Dashboard
DATASOURCE_IMPORT__BUILD_DASHBOARD = """
{% set is_rv = ti.xcom_pull(task_ids='internal.start', key='return_value') %}
{% set qj_rv = ti.xcom_pull(task_ids='internal.query_job', key='return_value') %}
process-dashboard-v1
--application-id refy-athena-import-test
--prediction {{ qj_rv['prediction'] }}
--client-id {{ qj_rv['client'] }}
--dashboard-title {{ is_rv['run_guid'] }}
--athena-schema {{ dag_run.conf['athena__schema_name'] }}
--superset-schema-path /app/tmp/{{ qj_rv['folder_path'] }}/{{ is_rv['datasource_export_filename'] }}
--output-path /app/tmp/{{ qj_rv['folder_path'] }}/{{ is_rv['dashboard_filename'] }}
"""
datasource_import__build_dashboard = DockerOperator(
    dag=dag,
    task_id='datasource_import.build_dashboard',
    image='refy-athena-import',
    xcom_push=True,
    volumes=[
        f'{DOCKER_VOLUME__DAG}:{DOCKER_VOLUME__DATASOURCE_IMPORT}'
    ],
    user='dataimp',
    environment=DATASOURCE_IMPORT__ENV,
    command=DATASOURCE_IMPORT__BUILD_DASHBOARD,
    on_success_callback=cb_chain(cb__json_deserialize, cb__httphook_report),
    on_failure_callback=cb__httphook_report
)


# Docker superset - Import Dashboards
SUPERSET__IMPORT_DASHBOARD = """
{% set is_rv = ti.xcom_pull(task_ids='internal.start', key='return_value') %}
{% set qj_rv = ti.xcom_pull(task_ids='internal.query_job', key='return_value') %}
import-dashboards
--path /app/superset_home/{{ qj_rv['folder_path'] }}/{{ is_rv['dashboard_filename'] }}
"""
superset__import_dashboard = DockerOperator(
    dag=dag,
    task_id='superset.import_dashboard',
    image='refy-superset_superset-cli',
    network_mode='host',
    volumes=[
        f'{DOCKER_VOLUME__DAG}:{DOCKER_VOLUME__SUPERSET}'
    ],
    user='superset',
    environment=SUPERSET__ENV,
    command=SUPERSET__IMPORT_DASHBOARD,
    on_success_callback=cb__httphook_report,
    on_failure_callback=cb__httphook_report
)


# Docker superset - Import Dashboards
SUPERSET__UPDATE_DASHBOARD = """
{% set is_rv = ti.xcom_pull(task_ids='internal.start', key='return_value') %}
{% set qj_rv = ti.xcom_pull(task_ids='internal.query_job', key='return_value') %}
update-dashboard
--dashboard-title {{ is_rv['run_guid'] }}
--slug {{ qj_rv['prediction'] }}
--new-title="{{ qj_rv['title'] }}"
"""
superset__update_dashboard = DockerOperator(
    dag=dag,
    task_id='superset.update_dashboard',
    image='refy-superset_superset-cli',
    network_mode='host',
    user='superset',
    environment=SUPERSET__ENV,
    command=SUPERSET__UPDATE_DASHBOARD,
    on_success_callback=cb__httphook_report,
    on_failure_callback=cb__httphook_report
)


# Python internal - Get refy Client Data
def query_client(*args, **kwargs):  # pylint: disable=unused-argument
    qj_rv = kwargs['ti'].xcom_pull(task_ids='internal.query_job', key='return_value')
    project = qj_rv['project']
    # Query Endpoint
    core_endpoint = HttpHook(method='GET', http_conn_id='users_endpoint')
    response = core_endpoint.run(
        f'/users_api/api/v1/users/{project}/list',
        headers={'Content-Type': 'application/json'}
    )
    users_rv = response.json()
    return users_rv


internal__query_client = PythonOperator(
    dag=dag,
    task_id='internal.query_client',
    python_callable=query_client,
    on_success_callback=cb__httphook_report,
    on_failure_callback=cb__httphook_report
)


# Create User DAG Run Callable
def create_users_dagrun(context):
    # Users DAta
    client_rv = context['ti'].xcom_pull(task_ids='internal.query_client', key='return_value')
    job_rv = context['ti'].xcom_pull(task_ids='internal.query_job', key='return_value')
    return [
        DagRunOrder(
            run_id=None,
            payload={
                'user': user,
                'role': job_rv['project'],
                'database': job_rv['client']
            }
        )
        for user in client_rv
    ]


internal__create_users_dagrun = MultipleTriggerDagRunOperator(
    dag=dag,
    task_id='trigger_dagrun.dashboard_user',
    trigger_dag_id='datasource_import_users_dag',
    python_callable=create_users_dagrun,
    on_success_callback=cb__httphook_report,
    on_failure_callback=cb__httphook_report
)


internal__end = DummyOperator(
    dag=dag,
    task_id='internal.end',
    trigger_rule=TriggerRule.ALL_DONE,
    on_success_callback=cb__httphook_report,
    on_failure_callback=cb__httphook_report
)


# Task Stream
internal__start\
    >> internal__query_job\
    >> ecs_datasource_import__build_datasource\
    >> superset__import_datasource\
    >> superset__export_datasource\
    >> datasource_import__build_dashboard\
    >> superset__import_dashboard\
    >> superset__update_dashboard\
    >> internal__end

superset__import_datasource\
    >> internal__query_client\
    >> internal__create_users_dagrun\
    >> internal__end
