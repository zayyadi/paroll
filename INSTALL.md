# Local Install — PostgreSQL, Redis, uv

Ubuntu 24.04, sudo user. `sudo` will prompt for password.

## 1. PostgreSQL 16

Matches `docker-compose.yml` (`postgres:16-alpine`).

```bash
sudo apt update
sudo apt install -y postgresql postgresql-contrib
sudo systemctl enable --now postgresql
pg_lsclusters
sudo -u postgres psql -c "SELECT version();"
```

Setup DB for paroll (defaults from `docker-compose.yml`):

```bash
sudo -u postgres psql <<'SQL'
CREATE USER payroll_user WITH PASSWORD 'payroll_password';
CREATE DATABASE payroll_db OWNER payroll_user;
GRANT ALL PRIVILEGES ON DATABASE payroll_db TO payroll_user;
SQL
```

`.env` (see `.env-example`):

```ini
DB_NAME=payroll_db
DB_USER=payroll_user
DB_PASSWORD=payroll_password
DB_HOST=127.0.0.1
DB_PORT=5432
```

Test:

```bash
PGPASSWORD=payroll_password psql -h 127.0.0.1 -U payroll_user -d payroll_db -c '\l'
```

## 2. Redis 7

Used for Celery broker (`CELERY_BROKER_URL`) and Channels cache (`REDIS_LOCATION`).

```bash
sudo apt install -y redis-server
sudo systemctl enable --now redis-server
sudo systemctl status redis-server --no-pager
redis-cli ping  # expect: PONG
redis-cli info server | grep redis_version
```

`.env`:

```ini
REDIS_HOST=127.0.0.1
REDIS_PORT=6379
CELERY_BROKER_URL=redis://127.0.0.1:6379/2
CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/2
REDIS_LOCATION=redis://127.0.0.1:6379/1
```

If `supervised no` in `/etc/redis/redis.conf`, set to `auto` then `sudo systemctl restart redis-server`.

## 3. uv

Project is Python 3.11 (`Dockerfile`), `requirements.txt` based.

Install:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.local/bin/env
uv --version
uv python install 3.11
```

Use in existing project:

```bash
cd /opt/usr/devs/paroll
uv venv --python 3.11
source .venv/bin/activate
uv pip install -r requirements.txt
```

Run without activating:

```bash
uv run --active python manage.py check
uv run --active python manage.py migrate
uv run --active redis-cli ping
```

Migrate to `pyproject.toml` (optional):

```bash
uv init --bare --python 3.11  # only if no pyproject.toml, then
uv add -r requirements.txt
uv sync
```

System libs for `weasyprint==61.2`, `pillow` in `requirements.txt`:

```bash
sudo apt install -y libpango-1.0-0 libpangoft2-1.0-0 libpangocairo-1.0-0 libcairo2 libgdk-pixbuf-2.0-0 libharfbuzz-subset0 libharfbuzz0b libopenjp2-7 libjpeg-turbo8
ldconfig -p | grep pango
python -c "from weasyprint import HTML; print('weasyprint ok')"
```
