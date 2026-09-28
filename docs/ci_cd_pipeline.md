# CI/CD Pipeline

This project uses a professional CI/CD flow built around GitHub Actions, Docker,
and a Docker-based VPS deployment. The goal is not only to deploy the payroll
SaaS safely, but also to make each stage understandable enough that a developer
can learn how production delivery works.

## Architecture

The delivery path has four gates:

1. **Pull request CI** proves the code can install, pass Django checks, keep
   migrations in sync, pass tests, and survive basic security scans.
2. **Docker build** proves the application can be packaged the same way it will
   run outside a laptop.
3. **Image publishing** stores an immutable release artifact in GitHub Container
   Registry with both `latest` and commit-SHA tags.
4. **Production deployment** pulls the approved image on the VPS, runs database
   migrations, collects static files, restarts services, and runs health checks.

The pipeline is deliberately artifact-based: production deploys an image that CI
already built, not an unverified set of files copied manually to the server.

## Branch Strategy

- Feature work happens on short-lived branches.
- Pull requests into `main` must pass `.github/workflows/ci.yml`.
- Merges to `main` build and publish a Docker image.
- Production deployments use the protected `production` GitHub environment.
- Hotfixes follow the same path: branch, pull request, CI, merge, deploy.

## Workflows

### Pull Request CI

Workflow: `.github/workflows/ci.yml`

What it does:

- Installs Python 3.11 dependencies from `requirements.txt`.
- Runs `python manage.py check --settings=core.settings_test`.
- Runs `python manage.py makemigrations --check --dry-run --settings=core.settings_test`.
- Runs `python manage.py test --settings=core.settings_test`.
- Runs `bandit` against application packages.
- Runs `pip-audit` against `requirements.txt`.
- Builds the Docker image after Django checks pass.

Why professionals use it:

- It catches missing migrations before they reach production.
- It keeps tests close to every change.
- It proves the container still builds before anyone tries to deploy.
- It gives reviewers objective evidence instead of relying on manual claims.

Common failures:

- **Install failure**: a package in `requirements.txt` is missing, incompatible,
  or needs OS libraries that the runner does not have.
- **Migration failure**: a model changed without a committed migration.
- **Test failure**: app behavior changed or the test environment needs a stable
  setting in `core.settings_test`.
- **Security scan failure**: the code or dependency tree has a known risk that
  must be fixed or consciously documented.

### Build And Deploy

Workflow: `.github/workflows/deploy.yml`

What it does:

- Builds the Docker image.
- Pushes it to GitHub Container Registry.
- Deploys to the VPS through SSH after the `production` environment gate.
- Runs `scripts/deploy.sh`.

Why professionals use it:

- The image tag is the release identity.
- The VPS does not need to build application code during deployment.
- GitHub environment protection allows manual approvals for production.
- The same deploy script can be run manually during incidents.

## Required GitHub Secrets

Configure these under repository or environment secrets:

- `VPS_HOST`: production server hostname or IP address.
- `VPS_USER`: SSH user that owns the app deployment directory.
- `VPS_SSH_KEY`: private key for that user.
- `PRODUCTION_ENV`: full contents of the production `.env` file.

`GITHUB_TOKEN` is provided automatically by GitHub Actions and is used to publish
images to GitHub Container Registry.

## Server Layout

Recommended VPS layout:

```text
/opt/payroll/paroll
├── docker-compose.yml
├── docker-compose.prod.yml
├── scripts/
├── .env
└── application source checkout
```

The deployment script defaults to `/opt/payroll/paroll` when run by the workflow.
Set `APP_DIR` if your path is different.

## Environment Files

Use `.env.example` as the canonical template for local and production
configuration. The older `.env-example` file is kept only as a compatibility
reference while the project transitions to the standard dotted name.

For production, keep secrets in GitHub as `PRODUCTION_ENV`. The deploy script
writes that secret to `.env` on the VPS with restrictive permissions before
starting services.

## Rollback Model

Every release image is tagged with the commit SHA. To roll back, redeploy the
last known-good image tag:

```bash
cd /opt/payroll/paroll
IMAGE_REF=ghcr.io/OWNER/REPOSITORY:PREVIOUS_SHA ./scripts/deploy.sh
```

Rollback rule:

- Roll back the app container first.
- Treat database rollback as a separate decision.
- Only reverse a migration when the migration is explicitly reversible and the
  data impact is understood.

## Learning Milestones

### Milestone 1: CI Only

Open a pull request and read every CI step. The goal is to understand what each
check proves before deployment exists.

Record:

- Which command failed first, if any.
- What the failure message meant.
- What code or config change fixed it.

### Milestone 2: Container Image Build

Confirm `podman build .` works locally and the image builds in CI. The goal is to learn the
difference between "runs on my laptop" and "runs from a production artifact".

Record:

- Image tag used.
- Build duration.
- Any missing runtime dependency found by the container build.

### Milestone 3: VPS Deployment

Run deployment against the VPS with the production environment configured. The
goal is to learn server-side release mechanics: pull, migrate, collect static,
restart, health check.

Record:

- Deployed commit SHA.
- Migration output.
- Health check result.

### Milestone 4: Production Approval And Rollback

Protect the `production` environment in GitHub and require approval. Then test a
rollback using a previous image tag.

Record:

- Who approved the deployment.
- Previous image tag.
- Rollback command used.

## Debugging Checklist

- Check GitHub Actions logs from top to bottom; fix the first real failure.
- Confirm `SECRET_KEY` and `DJANGO_SETTINGS_MODULE` are present in CI.
- Run the same failing command locally with `--settings=core.settings_test`.
- On the VPS, run `podman-compose ps` before reading logs.
- Read logs with `podman-compose logs --tail=200 web`.
- If Redis or PostgreSQL is unhealthy, fix infrastructure before app code.
- If migrations fail, do not keep restarting services; inspect the migration.
