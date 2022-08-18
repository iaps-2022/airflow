# syntax=docker/dockerfile:1.0-experimental
# Previous line is needed to override default frontend that translates into common LLB,
# In this case, this functionality is added so build secrets can be injected

# BUILD: docker build --rm -t airflow .
# ORIGINAL SOURCE: https://github.com/puckel/docker-airflow

# place this instruction force cache till this step
# ARG CACHE-STOP-MARK

FROM python:3.8.8-slim as build-os-airflow
LABEL version="1.2"
LABEL maintainer="refy-platform"

# Never prompts the user for choices on installation/configuration of packages
ENV DEBIAN_FRONTEND noninteractive
ENV TERM linux

# Airflow Configs
# it's possible to use v1-10-stable, but it's a development branch
ARG AIRFLOW_VERSION=1.10.15
ENV AIRFLOW_HOME=/usr/local/airflow
ENV AIRFLOW_GPL_UNIDECODE=yes
# celery config
ARG CELERY_REDIS_VERSION=4.4.7
ARG PYTHON_REDIS_VERSION=3.5.3

ARG TORNADO_VERSION=5.1.1
ARG WERKZEUG_VERSION=0.16.1
ARG SQLAlchemy=1.3.15


# Define en_US.
ENV LANGUAGE en_US.UTF-8
ENV LANG en_US.UTF-8
ENV LC_ALL en_US.UTF-8
ENV LC_CTYPE en_US.UTF-8
ENV LC_MESSAGES en_US.UTF-8
ENV LC_ALL en_US.UTF-8

# install dependencies & processes
RUN set -ex \
    && buildDeps=' \
        python3-dev \
        libkrb5-dev \
        libsasl2-dev \
        libssl-dev \
        libffi-dev \
        build-essential \
        libblas-dev \
        liblapack-dev \
        libpq-dev \
        apt-transport-https \
        software-properties-common \
    ' \
    && apt-get update -yqq \
    && apt-get upgrade -yqq \
    && apt-get install -yqq --no-install-recommends \
        ${buildDeps} \
        sudo \
        python3-pip \
        python3-requests \
        default-mysql-client \
        default-libmysqlclient-dev \
        apt-utils \
        curl \
        rsync \
        netcat \
        locales \
        git \
        ca-certificates \
        openssl \
    && apt-get install -yqq \
        gnupg-agent \
        fuse-overlayfs \
    && curl -fsSL https://download.docker.com/linux/debian/gpg | apt-key add - \
    && add-apt-repository \
        "deb [arch=amd64] https://download.docker.com/linux/debian \
        $(lsb_release -cs) \
        stable" \
    && apt-get update -yqq \
    && apt-get install -yqq --no-install-recommends \
        docker-ce \
        docker-ce-cli \
        containerd.io \
    && sed -i 's/^# en_US.UTF-8 UTF-8$/en_US.UTF-8 UTF-8/g' /etc/locale.gen \
    && locale-gen \
    && update-locale LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8 \
    && useradd -ms /bin/bash -d ${AIRFLOW_HOME} airflow \
    && pip install -U pip setuptools wheel \
    && pip install --no-cache-dir markupsafe==2.0.1 \
    && pip install --no-cache-dir pytz \
    && pip install --no-cache-dir pyOpenSSL \
    && pip install --no-cache-dir ndg-httpsclient \
    && pip install --no-cache-dir pyasn1 \
    && pip install --no-cache-dir typing_extensions \
    && pip install --no-cache-dir mysqlclient \
    && pip install --no-cache-dir SQLAlchemy==${SQLAlchemy} \
    && pip install --no-cache-dir apache-airflow[async,aws,crypto,celery,docker,github_enterprise,kubernetes,jdbc,postgres,password,s3,slack,ssh]==${AIRFLOW_VERSION} \
    && pip install --no-cache-dir werkzeug==${WERKZEUG_VERSION} \
    && pip install --no-cache-dir redis==${PYTHON_REDIS_VERSION} \
    && pip install --no-cache-dir celery[redis]==${CELERY_REDIS_VERSION} \
    && pip install --no-cache-dir flask_oauthlib \
    && pip install --no-cache-dir psycopg2-binary \
    && pip install --no-cache-dir tornado==${TORNADO_VERSION} \
    && pip install --no-cache-dir docker \
    && apt-get purge --auto-remove -yqq ${buildDeps} \
    && apt-get autoremove -yqq --purge \
    && apt-get clean \
    && rm -rf \
        /var/lib/apt/lists/* \
        /tmp/* \
        /var/tmp/* \
        /usr/share/man \
        /usr/share/doc \
        /usr/share/doc-base

# copying init script
COPY docker/docker-init.sh /docker-init.sh
RUN chmod +x /docker-init.sh

# copying entrypoint
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# configuring airflow process
COPY config/airflow.cfg ${AIRFLOW_HOME}/airflow.cfg
COPY dags ${AIRFLOW_HOME}/dags
COPY plugins ${AIRFLOW_HOME}/plugins

# configuring container user: airflow
RUN chown -R airflow: ${AIRFLOW_HOME}
ENV PYTHONPATH ${AIRFLOW_HOME}

RUN --mount=type=secret,id=sudo_password cat /run/secrets/sudo_password
RUN usermod -aG docker,sudo airflow
RUN usermod --password $(openssl passwd -1 $(cat /x)) airflow

USER airflow

# install airflow plugins
COPY plugins.txt .
RUN pip install --user --no-cache-dir -r plugins.txt

# install airflow env dependencies
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

EXPOSE 8080 5555 8793

WORKDIR ${AIRFLOW_HOME}

ENTRYPOINT [ "/entrypoint.sh" ]


FROM build-os-airflow as dev

# copying docker daemon config
COPY config/docker_daemon-config.json /etc/docker/daemon.json
