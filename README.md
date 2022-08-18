# refy-airflow-slim
#refy instructions

We have forced Airflow version to 1.10.14 due compatibility issues.

##Setup steps

1.- Generate a fernet key and set up env var in docker/.env (if the command does not work, look for python code to generate a fernet key in Google)
```
dd if=/dev/urandom bs=32 count=1 2>/dev/null | openssl base64
```
2.- run this command locally
```
docker build -f Dockerfile-new -t airflow . --no-cache
```
2.- run docker compose up. Docker compose up should populate a database with basic setup.
```
docker compose up
```
3.- After some **minutes**, airflow should be available at http://localhost:8080. Default Login data is available in docker/.env (set up via docker/docker-init.sh) 

4.- To run a dag, the dag should be copied into the dags folder. (configurable via env var)

# Old info (keep for reference)
## refy-airflow-slim

Current Version v1.10.15 (due to upgrade to v2.x.y)

This repository is based on the previous work of NicolaCorda: 
[nicor88/aws-ecs-airflow](https://github.com/nicor88/aws-ecs-airflow)

## How to run

** Local Development **

1.  Populate .env files as required (inside /env folder, some defaults are provided. Whatever you do, please don't use this ones in production :disappointed:)  
  
2.  Building and running locally. This will take some time :hourglass: In the meantime enjoy some :coffee: or :tea: (we don't discriminate)
  
    ```
    make airflow-up
    ```  
    ##  
  this will build the "dev" targeted image & the following containers will get launched:

    *  refy-airflow-slim_webserver_1
    *  refy-airflow-slim_postgres_1
    *  refy-airflow-slim_flower_1
    *  refy-airflow-slim_redis_1
    *  refy-airflow-slim_scheduler_1
    *  refy-airflow-slim_worker_1
    * _refy-airflow-slim_webserver-init (this is just a temporal instance that will seed initial config)_



- Note: The defaults run a _Celery Executor_ & not the typical _Serial Executor_.

##  
** Production Image **

1.  To build the production target image, just run the following command:

    ```
	make build-prod
    ```

##  
** Creating Tasks **

As a rule here at refy, each task must be implemented as a Docker image. The implications of this, and with 
the purpose of keeping code clean and decoupled, you must create a repository for each new _Task Type_ that you want
to use inside a production DAG. If there is already a _Task_ that suits your need, then use that one.

For local testing purposes you can just build the image locally on your host and then upload it to the provided registry
so that airflow will be able to pull the image from the provided registry.

##
** Creating DAGs **

Inside the folder "/.../..." you can see and example of a DAG that uses some provided example images


-----------------------
##  
**(Old Doc, TODO strip only needed content and delete the rest)**

##
## Original Readme
##
# airflow-ecs
Setup to run Airflow in AWS ECS containers

## Requirements

### Local
* Docker

### AWS
* AWS IAM User for the infrastructure deployment, with admin permissions
* [awscli](https://aws.amazon.com/cli/), intall running `pip install awscli`
* [terraform >= 0.13](https://www.terraform.io/downloads.html)
* setup your IAM User credentials inside `~/.aws/credentials`
* setup these env variables in your .zshrc or .bashrc, or in your the terminal session that you are going to use
  <pre>
  export AWS_ACCOUNT=your_account_id
  export AWS_DEFAULT_REGION=us-east-1 # it's the default region that needs to be setup also in infrastructure/config.tf
  </pre>


## Local Development
* Generate a Fernet Key:
  <pre>
  pip install cryptography
  export AIRFLOW_FERNET_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
  </pre>
  More about that [here](https://cryptography.io/en/latest/fernet/)

* Start Airflow locally simply running:
  <pre>
  docker-compose up --build
  </pre

If everything runs correctly you can reach Airflow navigating to [localhost:8080](http://localhost:8080).
The current setup is based on [Celery Workers](https://airflow.apache.org/howto/executor/use-celery.html). You can monitor how many workers are currently active using Flower, visiting [localhost:5555](http://localhost:5555)

## Deploy Airflow on AWS ECS
To run Airflow in AWS we will use ECS (Elastic Container Service).

### Deploy Infrastructure using Terraform
Run the following commands:
<pre>
make infra-init
make infra-plan
make infra-apply
</pre>

or alternatively
<pre>
cd infrastructure
terraform get
terraform init -upgrade;
terraform plan
terraform apply
</pre>

By default the infrastructure is deployed in `us-east-1`.

When the infrastructure is provisioned (the RDS metadata DB will take a while) check the if the ECR repository is created then run:
<pre>
bash scripts/push_to_ecr.sh airflow-dev
</pre>
By default the repo name created with terraform is `airflow-dev`
Without this command the ECS services will fail to fetch the `latest` image from ECR

### Deploy new Airflow application
To deploy an update version of Airflow you need to push a new container image to ECR.
You can simply doing that running:
<pre>
./scripts/deploy.sh airflow-dev
</pre>

The deployment script will take care of:
* push a new ECR image to your repository
* re-deploy the new ECS services with the updated image

## TODO
* Create Private Subnets
* Move ECS containers to Private Subnets
* Use ECS private Links for Private Subnets
* Improve ECS Task and Service Role
-----------------------

## Validating Files

For runing validation over dataSources you can use the provided DAG example "dags/data_validation_dag.py"
Some things that need to be done before are:

### 1-.Create a bootstrap shell script and upload it to an S3 bucket. The following code is an example of pydeequ-emr-bootstrap.sh:

```
#!/bin/bash

sudo python3 -m pip install --no-deps pydeequ
```

### 2- Change the boot-strap-action to be loaded from the correct S3 PATH (inside "data_validation_dag.py")
Change <S3_PATH_TO_BOOTSTRAP> for the corresponding S3 bucket and path to sh script

### 3- Then inside the t2 (task) from the DAG you would submit a step to the EMR cluster using the provided clustername & dataSourceCode

pre-requisits:
Access to dockrhub configured to pull images

Airflow Process must have Role that enables creation and termination of EMR Clusters
