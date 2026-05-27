# Repository Organization

This project is a Django payroll, HR, inventory, accounting, and API application.

## Core Django Project

- `core/` - Django settings, URL routing, ASGI/WSGI entrypoints, and Celery setup.
- `manage.py` - Django management entrypoint.
- `requirements.txt` - Python dependency list.

## Domain Apps

- `payroll/` - Payroll, HR, employee lifecycle, hiring, attendance, benefits, documents, appraisals, and notifications.
- `accounting/` - Ledger, journals, reporting, disciplinary workflows, fiscal periods, and accounting controls.
- `inventory/` - Inventory items, stock movements, purchase orders, suppliers, warehouses, and inventory approval workflows.
- `company/` - Tenant/company membership, active-company scoping, and company-level helpers.
- `users/` - Authentication, registration, profile, password reset, and user email flows.
- `api/` - API views, serializers, and v1 viewsets.
- `integrations/` - External service integration models, services, and tests.
- `marketing/` - Public marketing pages.
- `monthyear/` - Custom month/year field and widget.

## Tests

- App-local tests live beside their app, for example `payroll/tests.py`, `payroll/test_views.py`, and `accounting/tests/`.
- Cross-app tests live in `tests/`.
- Prefer adding narrow regression tests next to the code being changed.

## Templates And Static Assets

- `templates/` - Django templates grouped by domain: `employee/`, `inventory/`, `accounting/`, `pay/`, `registration/`, and email templates.
- `static/` - Source/static vendor assets used by templates.
- `staticfiles/` - Generated collectstatic output and should remain untracked.
- `media/` - Local uploaded/sample media. Treat production uploads as runtime data, not source code.

## Generated Or Local-Only Files

The repository should not track generated Python bytecode, test caches, local virtual environments, local database files, or runtime state. See `.gitignore` for the canonical ignore list.

## Current Workflow Notes

- Use Django migrations for model changes.
- Use `venv/bin/python manage.py check` for a quick health check.
- Use `venv/bin/python manage.py test <module> --settings=core.settings_test` for targeted verification.
- Keep inventory/accounting/HR approval behavior covered with regression tests before refactors.
