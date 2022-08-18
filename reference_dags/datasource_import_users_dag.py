from datetime import datetime, timedelta
from airflow import DAG
from airflow.models import Variable
from airflow.exceptions import AirflowFailException
from airflow.operators.docker_operator import DockerOperator
from airflow.operators.dummy_operator import DummyOperator
from airflow.operators.python_operator import (
    PythonOperator,
    BranchPythonOperator
)
from airflow.utils.trigger_rule import TriggerRule

AWS_ENV = Variable.get('aws__env', deserialize_json=True)
# Superset ENV Variables
SUPERSET__ENV = Variable.get('superset__env', deserialize_json=True)
SUPERSET__ENV.update(AWS_ENV)


# DAG definition
default_args = {
    'owner': 'refy-platform',
    'start_date': datetime(2021, 2, 9),
    'depends_on_past': False,
    'provide_context': True,
    'pool': 'superset_users',
    'retries': 0
}

dag = DAG(
    'datasource_import_users_dag',
    description='Datasource Import - Create Users DAG',
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
        'user',
        'role'
    )
    # Check required conf key
    for conf_key in required_keys:
        if conf_key not in kwargs['dag_run'].conf:
            raise AirflowFailException(f'Missing Airflow conf value: {conf_key}')


internal__start = PythonOperator(
    dag=dag,
    task_id='internal.start',
    python_callable=internal_start
)


# superset Docker - User and Roles
SUPERSET__CREATE_USER = """
fab create-user
--username "{{ dag_run.conf['user']['username'] }}"
--password "{{ dag_run.conf['user']['username'] }}"
--firstname "{{ dag_run.conf['user']['first_name'] }}"
--lastname "{{ dag_run.conf['user']['last_name'] }}"
--email "{{ dag_run.conf['user']['email'] }}"
--role VIEW_ROLE
"""
superset__create_user = DockerOperator(
    dag=dag,
    task_id='superset.create_user',
    image='refy-superset_superset-cli',
    execution_timeout=timedelta(seconds=15),
    network_mode='host',
    user='superset',
    environment=SUPERSET__ENV,
    command=SUPERSET__CREATE_USER
)


# superset Docker - User and Roles
SUPERSET__USER_ROLES = """
set-user-role
--username {{ dag_run.conf['user']['username'] }}
--roles {{ dag_run.conf['role'] }}
"""
superset__user_roles = DockerOperator(
    dag=dag,
    task_id='superset.user_roles',
    image='refy-superset_superset-cli',
    network_mode='host',
    user='superset',
    environment=SUPERSET__ENV,
    command=SUPERSET__USER_ROLES,
    trigger_rule=TriggerRule.ALL_DONE
)


# superset Docker - DB Permissions
def database_branch(**kwargs):
    dag_run = kwargs['dag_run']
    if 'database' in dag_run.conf:
        return 'superset.role_permissions'
    return 'internal.end'


internal__database_branch = BranchPythonOperator(
    dag=dag,
    task_id='internal.database_branch',
    python_callable=database_branch,
)


# superset Docker - DB Permissions
SUPERSET__DB_PERMISSIONS = """
set-role-db-permissions
--database {{ dag_run.conf['database'] }}
--roles {{ dag_run.conf['role'] }}
"""
superset__role_permissions = DockerOperator(
    dag=dag,
    task_id='superset.role_permissions',
    image='refy-superset_superset-cli',
    network_mode='host',
    user='superset',
    environment=SUPERSET__ENV,
    command=SUPERSET__DB_PERMISSIONS
)


internal__end = DummyOperator(
    dag=dag,
    task_id='internal.end',
    trigger_rule=TriggerRule.NONE_FAILED
)


# Task Stream
internal__start\
    >> superset__create_user\
    >> superset__user_roles\
    >> internal__database_branch

internal__database_branch\
    >> superset__role_permissions\
    >> internal__end

internal__database_branch\
    >> internal__end
