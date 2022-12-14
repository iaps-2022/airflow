#!/usr/bin/env bash

#!/usr/bin/env bash

TRY_LOOP="20"

: "${REDIS_HOST:="redis"}"
: "${REDIS_PORT:="6379"}"

: "${POSTGRES_HOST:="postgres"}"
: "${POSTGRES_PORT:="5432"}"

wait_for_port() {
  local name="$1" host="$2" port="$3"
  local j=0
  while ! nc -z "$host" "$port" >/dev/null 2>&1 < /dev/null; do
    j=$((j+1))
    if [ $j -ge $TRY_LOOP ]; then
      echo >&2 "$(date) - $host:$port still not reachable, giving up"
      exit 1
    fi
    echo "$(date) - waiting for $name... $j/$TRY_LOOP"
    sleep 5
  done
}


wait_for_port "Postgres" "$POSTGRES_HOST" "$POSTGRES_PORT"

wait_for_port "Redis" "$REDIS_HOST" "$REDIS_PORT"

echo "running INIT DB"
airflow initdb

airflow create_user \
    -r Admin \
    -u $LOCAL_ADMIN_USERNAME \
    -e $LOCAL_ADMIN_EMAIL \
    -f $LOCAL_ADMIN_FIRST_NAME \
    -l $LOCAL_ADMIN_LAST_NAME \
    -p $LOCAL_ADMIN_PASSWORD

airflow connections --add \
    --conn_login $DHUB_CONN_LOGIN \
    --conn_password $DHUB_CONN_PASSWORD \
    --conn_type docker \
    --conn_host https://index.docker.io/v1/ \
    --conn_id $DHUB_ID
