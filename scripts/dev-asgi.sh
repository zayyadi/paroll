#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-venv/bin/python}"
ASGI_HOST="${ASGI_HOST:-0.0.0.0}"
ASGI_PORT="${ASGI_PORT:-8001}"
DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-core.settings}"

export DJANGO_SETTINGS_MODULE

exec "${PYTHON_BIN}" -m daphne -b "${ASGI_HOST}" -p "${ASGI_PORT}" core.asgi:application
