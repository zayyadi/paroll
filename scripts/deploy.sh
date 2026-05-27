#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-$(pwd)}"
ENV_FILE="${ENV_FILE:-.env}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
PROD_COMPOSE_FILE="${PROD_COMPOSE_FILE:-docker-compose.prod.yml}"
IMAGE_REF="${IMAGE_REF:-}"
RUN_HEALTHCHECK="${RUN_HEALTHCHECK:-1}"

cd "$APP_DIR"

if [[ -n "${PRODUCTION_ENV:-}" ]]; then
  umask 077
  printf '%s\n' "$PRODUCTION_ENV" > "$ENV_FILE"
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE. Create it from .env.example or provide PRODUCTION_ENV." >&2
  exit 1
fi

if [[ -n "$IMAGE_REF" ]]; then
  export IMAGE_REF
  docker compose --env-file "$ENV_FILE" -f "$PROD_COMPOSE_FILE" pull web celery-worker celery-beat daphne
  docker compose --env-file "$ENV_FILE" -f "$PROD_COMPOSE_FILE" up -d db redis
  docker compose --env-file "$ENV_FILE" -f "$PROD_COMPOSE_FILE" up -d web celery-worker celery-beat daphne
  COMPOSE_ARGS=(--env-file "$ENV_FILE" -f "$PROD_COMPOSE_FILE")
else
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d --build
  COMPOSE_ARGS=(--env-file "$ENV_FILE" -f "$COMPOSE_FILE")
fi

docker compose "${COMPOSE_ARGS[@]}" exec -T web python manage.py migrate --noinput
docker compose "${COMPOSE_ARGS[@]}" exec -T web python manage.py collectstatic --noinput

docker compose "${COMPOSE_ARGS[@]}" up -d --remove-orphans

if [[ "$RUN_HEALTHCHECK" == "1" ]]; then
  ENV_FILE="$ENV_FILE" IMAGE_REF="$IMAGE_REF" ./scripts/healthcheck.sh
fi
