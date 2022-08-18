from airflow import DAG
from airflow.operators.bash_operator import BashOperator
from datetime import datetime, timedelta
from airflow.operators.docker_operator import DockerOperator

default_args = {
    'owner'             : 'airflow',
    'description'       : 'Data Exploration',
    'depend_on_past'    : False,
    'start_date'        : datetime(2020, 12, 10),
    'email_on_failure'  : False,
    'email_on_retry'    : False,
    'retries'           : 1,
    'retry_delay'       : timedelta(minutes=5)
}

with DAG('test', default_args=default_args, schedule_interval=None, catchup=False) as dag:
    t1 = BashOperator(
        task_id='signal_initiation',
        bash_command= 'echo "starting "'
    )

    t2 = DockerOperator(
        docker_conn_id='docker_hub_refy',
        task_id='docker_test',
        image='debian:buster-slim',
        command=["uname"],
        api_version='auto',
        auto_remove=True,
    )

    t3 = BashOperator(
        task_id='signal_end',
        bash_command = 'echo "ending"'
    )

t1 >> t2 >> t3
