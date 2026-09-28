# Deployment Runbook

This runbook describes how to prepare, deploy, verify, and roll back the payroll
SaaS on a Docker-based VPS.

## First-Time VPS Setup

1. Install Podman and podman-compose.
2. Create a deployment user (rootless; enable linger so services survive logout):

   ```bash
   sudo adduser deploy
   sudo loginctl enable-linger deploy
   ```

3. Create the app directory:

   ```bash
   sudo mkdir -p /opt/payroll/paroll
   sudo chown -R deploy:deploy /opt/payroll
   ```

4. Clone the repository:

   ```bash
   git clone git@github.com:OWNER/REPOSITORY.git /opt/payroll/paroll
   cd /opt/payroll/paroll
   ```

5. Create `.env` from `.env.example` or let GitHub Actions write it from the
   `PRODUCTION_ENV` secret.

6. Log in to GitHub Container Registry if deploying manually:

   ```bash
   echo "TOKEN" | podman login ghcr.io -u "OWNER" --password-stdin
   ```

## Required Environment

Minimum production values:

```env
DEBUG=False
SECRET_KEY=replace-with-long-random-secret
ALLOWED_HOSTS=payroll.example.com
CSRF_TRUSTED_ORIGINS=https://payroll.example.com
DJANGO_SETTINGS_MODULE=core.settings_saas
DB_NAME=payroll
DB_USER=payroll
DB_PASSWORD=replace-with-database-password
DB_HOST=db
DB_PORT=5432
REDIS_LOCATION=redis://redis:6379/1
CELERY_BROKER_URL=redis://redis:6379/2
CELERY_RESULT_BACKEND=redis://redis:6379/2
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
```

Use `db` and `redis` as hostnames when the database and Redis run inside Docker
Compose. Use external hostnames only when those services are outside Compose.

## Deploy From GitHub Actions

1. Push or merge into `main`.
2. Open the **Build And Deploy** workflow.
3. Approve the `production` environment gate if configured.
4. Wait for the remote deploy step to finish.
5. Confirm the health check output shows:
   - Docker services running.
   - Django system check passing.
   - Database connectivity passing.
   - Cache connectivity passing.
   - Celery worker responding.
   - Web and Daphne HTTP responses below 500.

## Manual Deploy

Use this when practicing or recovering from a GitHub Actions outage:

```bash
cd /opt/payroll/paroll
git fetch --prune origin
git checkout main
git pull --ff-only origin main
IMAGE_REF=ghcr.io/OWNER/REPOSITORY:COMMIT_SHA ./scripts/deploy.sh
```

For a source-based deploy without a registry image:

```bash
cd /opt/payroll/paroll
git pull --ff-only origin main
./scripts/deploy.sh
```

The source-based path is useful for learning and emergencies, but the preferred
professional path is image-based deployment.

## Verification

Run:

```bash
cd /opt/payroll/paroll
IMAGE_REF=ghcr.io/OWNER/REPOSITORY:COMMIT_SHA ./scripts/healthcheck.sh
```

Useful follow-up commands:

```bash
podman-compose ps
podman-compose logs --tail=200 web
podman-compose logs --tail=200 celery-worker
podman-compose logs --tail=200 daphne
podman-compose exec -T web python manage.py showmigrations
```

## Rollback

Rollback to the previous image tag:

```bash
cd /opt/payroll/paroll
IMAGE_REF=ghcr.io/OWNER/REPOSITORY:PREVIOUS_SHA ./scripts/deploy.sh
```

Then verify:

```bash
IMAGE_REF=ghcr.io/OWNER/REPOSITORY:PREVIOUS_SHA ./scripts/healthcheck.sh
```

Do not automatically reverse database migrations during rollback. If a migration
changed data, inspect it and decide whether a forward fix is safer.

## Common Failures

### CI Cannot Install Dependencies

Run locally:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If the failure is an OS package requirement, add the OS package to the workflow
or the Dockerfile rather than hiding the error.

### Missing Migration

Run:

```bash
python manage.py makemigrations --check --dry-run --settings=core.settings_test
```

If Django reports changes, create and commit the migration.

### Deploy Cannot Pull Image

Check:

- The image exists in GitHub Container Registry.
- The server logged in with a token that can read packages.
- `IMAGE_REF` has the expected owner, repository, and SHA tag.

### Web Starts But Static Files Are Missing

Run:

```bash
podman-compose exec -T web python manage.py collectstatic --noinput
podman-compose restart web daphne
```

Then check reverse proxy static file routing.

### Celery Does Not Respond

Run:

```bash
podman-compose logs --tail=200 celery-worker
podman-compose exec -T celery-worker celery -A core inspect ping --timeout=10
```

Check Redis first. Celery cannot recover if the broker is unavailable.
