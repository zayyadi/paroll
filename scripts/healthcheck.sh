#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${ENV_FILE:-.env}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
PROD_COMPOSE_FILE="${PROD_COMPOSE_FILE:-docker-compose.prod.yml}"
WEB_URL="${WEB_URL:-http://127.0.0.1:8000/health/}"
DAPHNE_URL="${DAPHNE_URL:-http://127.0.0.1:8001/health/}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
COMPOSE_BIN="${COMPOSE_BIN:-podman-compose}"

if ! command -v "$COMPOSE_BIN" >/dev/null 2>&1 && podman compose version >/dev/null 2>&1; then
  COMPOSE_BIN="podman compose"
fi
# shellcheck disable=SC2206
COMPOSE=($COMPOSE_BIN)

if [[ -n "${IMAGE_REF:-}" && -f "$PROD_COMPOSE_FILE" ]]; then
  export IMAGE_REF
  COMPOSE_ARGS=(--env-file "$ENV_FILE" -f "$PROD_COMPOSE_FILE")
else
  COMPOSE_ARGS=(--env-file "$ENV_FILE" -f "$COMPOSE_FILE")
fi

"${COMPOSE[@]}" "${COMPOSE_ARGS[@]}" ps

"${COMPOSE[@]}" "${COMPOSE_ARGS[@]}" exec -T web python manage.py check
"${COMPOSE[@]}" "${COMPOSE_ARGS[@]}" exec -T web python - <<'PY'
from django.db import connection

with connection.cursor() as cursor:
    cursor.execute("SELECT 1")
    assert cursor.fetchone()[0] == 1
print("database: ok")
PY

"${COMPOSE[@]}" "${COMPOSE_ARGS[@]}" exec -T web python - <<'PY'
from django.core.cache import cache

cache.set("healthcheck", "ok", 10)
assert cache.get("healthcheck") == "ok"
print("cache: ok")
PY

"${COMPOSE[@]}" "${COMPOSE_ARGS[@]}" exec -T celery-worker celery -A core inspect ping --timeout=10

"$PYTHON_BIN" - <<PY
from urllib.request import urlopen

for name, url in {"web": "$WEB_URL", "daphne": "$DAPHNE_URL"}.items():
    with urlopen(url, timeout=10) as response:
        if response.status >= 500:
            raise SystemExit(f"{name}: unhealthy status {response.status}")
        print(f"{name}: http {response.status}")
PY
