airflow-up:
	@DOCKER_BUILDKIT=1 docker build \
	--rm \
	-f Dockerfile-new \
	--target dev \
	-t airflow:latest \
	--secret id=x,src=x.txt \
	. \
	&& docker-compose up;

airflow-constraints := $$(cat airflow-constraints.txt | sed 's@^@--build-arg @g' | paste -s -d " ")

airflow-up-without-delete:
	@DOCKER_BUILDKIT=1 docker build --target dev -t airflow:latest --secret id=x,src=x.txt . && docker-compose up
	# still experimental, support for BuildKit will has been added in Docker Compose 1.25.0
	#@COMPOSE_DOCKER_CLI_BUILD=1 DOCKER_BUILDKIT=1 docker-compose build && docker-compose up;

airflow-up_cache-till-mark:
	@DOCKER_BUILDKIT=1 docker build --target dev --build-arg CACHE-STOP-MARK=$(date +%s) -t airflow:latest --secret id=x,src=x.txt . && docker-compose up

airflow-up_no-cache:
	@DOCKER_BUILDKIT=1 docker build --rm --target dev --no-cache -t airflow:latest --secret id=x,src=x.txt . && docker-compose up
	
airflow-down:
	@docker-compose down

infra-get:
	cd infrastructure && terraform get;

infra-init: infra-get
	cd infrastructure && terraform init -upgrade;

infra-plan: infra-init
	cd infrastructure && terraform plan;

infra-apply: infra-plan
	cd infrastructure && terraform apply;

infra-destroy:
	cd infrastructure && terraform destroy;

clean:
	rm -rf postgres_data
