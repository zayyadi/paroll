# Payroll SaaS Platform (Django)

Multi-tenant payroll and employee management SaaS built with Django, Celery, Channels, PostgreSQL, and Redis.

## SaaS Model

- Tenancy model: shared database, shared schema, row-level tenant isolation by `company`.
- Workspace identity: `Company` + `CompanyMembership` (`owner`, `admin`, `member`).
- Active tenant resolution: user `active_company`, request-level `tenant_company`, and tenant context processor.
- Tenant guard: `company.middleware.ActiveCompanyMiddleware` blocks authenticated non-superusers with no active company when SaaS enforcement is enabled.

## Core Modules

- `payroll/`: employee lifecycle, payroll runs, leave, IOU, payslips, reports.
- `accounting/`: journals, periods, fiscal year workflows, audit.
- `company/`: tenant/company model, membership, tenant utilities and SaaS management command.
- `users/`: auth, registration, OTP, company switch flow.
- `api/`: DRF endpoints scoped to active tenant.

## Quick Start (Local)

1. Create and activate venv.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Configure env:
   ```bash
   cp .env-example .env
   ```
4. Run migrations:
   ```bash
   python manage.py migrate
   ```
5. Create superuser:
   ```bash
   python manage.py createsuperuser
   ```
6. Start app:
   ```bash
   python manage.py runserver
   ```

## Tenant Onboarding

Create a new tenant workspace and owner user:

```bash
python manage.py create_tenant "Acme Inc" owner@acme.com --owner-password "ChangeMe123!"
```

If the user already exists:

```bash
python manage.py create_tenant "Acme Inc" owner@acme.com --existing-user
```

## SaaS Settings

Use the SaaS settings overlay in deployment:

```bash
DJANGO_SETTINGS_MODULE=core.settings_saas
```

Important env vars:

- `MULTI_COMPANY_MEMBERSHIP_ENABLED`
- `SAAS_ENFORCE_ACTIVE_COMPANY`
- `ALLOWED_HOSTS`
- `CSRF_TRUSTED_ORIGINS`
- `SECURE_SSL_REDIRECT`
- `SESSION_COOKIE_SECURE`
- `CSRF_COOKIE_SECURE`

See `.env-example` for defaults.

## Docker Compose

`docker-compose.yml` includes:

- `web` (gunicorn)
- `db` (PostgreSQL)
- `redis`
- `celery-worker`
- `celery-beat`
- `daphne` (ASGI)

Run:

```bash
docker compose up --build
```

## Tenant Isolation Notes

- Payroll/API read paths are scoped to the active company.
- Leave policies and public holidays are tenant-scoped (`company` FK).
- Company-switch endpoint updates `active_company` for multi-company users.

## Tests

Run:

```bash
python manage.py test company
```

Add broader regression tests before production release:

```bash
python manage.py test
```
