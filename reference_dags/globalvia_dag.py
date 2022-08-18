from airflow import DAG
from datetime import datetime, timedelta
from airflow.operators.bash_operator import BashOperator
from airflow.operators.docker_operator import DockerOperator

default_args = {
    'owner'             : 'airflow',
    'description'       : 'globalvia-post-process',
    'depend_on_past'    : False,
    'start_date'        : datetime(2020, 11, 27),
    'email_on_failure'  : False,
    'email_on_retry'    : False,
    'retries'           : 1,
    'retry_delay'       : timedelta(minutes=5)
}

with DAG('globalvia-post-process', default_args=default_args, schedule_interval=None, catchup=False) as dag:
    t1 = BashOperator(
        task_id='provision_emr_cluster',
        bash_command= 'aws emr create-cluster \
                        --name validation-emr-cluster \
                        --use-default-roles \
                        --release-label emr-5.31.0 \
                        --applications Name=Spark Name=Hadoop Name=Hive Name=Livy Name=Pig Name=Hue \
			--instance-type m5.xlarge \
                        --instance-count 3 \
                        --log-uri s3://s3-for-emr-cluster/'
    )

    t2 = DockerOperator(
        task_id='validation run',
        image='refyai/globalvia-post-process',
        api_version='auto',
        auto_remove=True,
        docker_url='unix://var/run/docker.sock',
        docker_conn_id='dhub_registry-refyai',
        force_pull=True,
        network_mode='bridge',
        environment={	
		"clusterName": "validation-emr-cluster",
		 // "PASS ALL PARAMETERS HERE!!!!" with dag_run.conf[""],
	}
    )

    t3 = BashOperator(
        task_id='terminate_emr_cluster',
        bash_command='aws emr terminate-clusters --cluster-ids validation-emr-cluster'
    )

    t1 >> t2 >> t3
