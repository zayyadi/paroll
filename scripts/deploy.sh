#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-$(pwd)}"
ENV_FILE="${ENV_FILE:-.env}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
PROD_COMPOSE_FILE="${PROD_COMPOSE_FILE:-docker-compose.prod.yml}"
IMAGE_REF="${IMAGE_REF:-}"
RUN_HEALTHCHECK="${RUN_HEALTHCHECK:-1}"
# Podman-first: override e.g. COMPOSE_BIN="podman compose" if the compose plugin is installed.
COMPOSE_BIN="${COMPOSE_BIN:-podman-compose}"

if ! command -v "$COMPOSE_BIN" >/dev/null 2>&1 && podman compose version >/dev/null 2>&1; then
  COMPOSE_BIN="podman compose"
fi
# Split "podman compose" into an array if the plugin form is used.
# shellcheck disable=SC2206
COMPOSE=($COMPOSE_BIN)

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
  "${COMPOSE[@]}" --env-file "$ENV_FILE" -f "$PROD_COMPOSE_FILE" pull web celery-worker celery-beat daphne
  "${COMPOSE[@]}" --env-file "$ENV_FILE" -f "$PROD_COMPOSE_FILE" up -d db redis
  "${COMPOSE[@]}" --env-file "$ENV_FILE" -f "$PROD_COMPOSE_FILE" up -d web celery-worker celery-beat daphne
  COMPOSE_ARGS=(--env-file "$ENV_FILE" -f "$PROD_COMPOSE_FILE")
else
  "${COMPOSE[@]}" --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d --build
  COMPOSE_ARGS=(--env-file "$ENV_FILE" -f "$COMPOSE_FILE")
fi

"${COMPOSE[@]}" "${COMPOSE_ARGS[@]}" exec -T web python manage.py migrate --noinput
"${COMPOSE[@]}" "${COMPOSE_ARGS[@]}" exec -T web python manage.py collectstatic --noinput

"${COMPOSE[@]}" "${COMPOSE_ARGS[@]}" up -d --remove-orphans

if [[ "$RUN_HEALTHCHECK" == "1" ]]; then
  ENV_FILE="$ENV_FILE" IMAGE_REF="$IMAGE_REF" COMPOSE_BIN="$COMPOSE_BIN" ./scripts/healthcheck.sh
fi
