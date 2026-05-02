# Production Readiness

This app handles payroll, employee records, leave, IOU, payslips, and accounting
data. Treat every production deployment as sensitive-data infrastructure.

## Required Environment

Use `core.settings_saas` for production deployments and set values from
`.env.example` in the host environment or a secrets manager. Do not deploy with
`DEBUG=True`.

Rotate any secrets that have ever been stored in a local `.env`, especially:

- `SECRET_KEY`
- database password
- email provider credentials
- API keys

## Security Defaults

The default settings now harden production when `DEBUG=False`:

- HTTPS redirect defaults on.
- HSTS defaults to one year.
- secure session and CSRF cookies default on.
- `X_FRAME_OPTIONS` defaults to `DENY`.
- accounting access defaults to superuser-only until tenant scoping is complete.

Test settings explicitly disable HTTPS redirects so Django's test client can run
without production transport behavior.

## Release Checklist

Before every production release:

1. Run `python manage.py check --deploy --settings=core.settings_saas`.
2. Run `python manage.py makemigrations --check --dry-run --settings=core.settings_test`.
3. Run the focused test suite for changed areas.
4. Confirm `git status --short` contains only intentional files.
5. Apply migrations with `python manage.py migrate --settings=core.settings_saas`.
6. Run Celery workers for the configured queues:

   ```bash
   celery -A core worker -Q notifications_critical,notifications_high,notifications_normal,notifications_low -l INFO
   celery -A core beat -l INFO
   ```

## Current Verification Gaps

`python manage.py test --settings=core.settings_test` now discovers the full test
suite, but the suite is not yet green. The remaining failures are outside the
hardening fixes and should be handled before production release:

- legacy accounting tests import utility functions that no longer exist;
- legacy accounting tests still pass `username` to the custom email-only user
  model;
- root-level scratch tests under `tests/` import as real tests and include a
  syntax error;
- several payroll tax and standup tests fail current business logic
  expectations.

Keep the focused production hardening suite green while these older tests are
repaired.

## Celery Queues

Queue declarations live in `CELERY_TASK_QUEUES`. Task-to-queue routing lives in
`CELERY_TASK_ROUTES`. Keep these separate so queue topology is not overwritten by
task routing.

Payslip email jobs route to `notifications_normal`. Digest and cleanup tasks
route to `notifications_low`.

Notification email delivery renders `templates/notifications/email/<TYPE>.html`
and `.txt` first, then falls back to `templates/notifications/email/default.html`
and `.txt` for notification types without a custom template. Keep the default
templates present in every deployment; otherwise Celery workers will mark email
delivery as failed with `TemplateDoesNotExist`.

Push and SMS delivery require device tokens and recipient phone numbers. If those
channels are not active for the product, disable them in notification
preferences instead of treating "No device tokens found" or "Recipient phone
number not found" as worker crashes.

For local Redis queue inspection:

```bash
redis-cli -n 2 LLEN notifications_normal
redis-cli -n 2 LLEN notifications_low
```

For payslip email recovery without the admin UI:

```bash
python manage.py process_payslip_email_jobs --status failed --limit 25
```

## Frontend Assets

Shared layouts use local static copies of Tailwind's runtime script and Lucide
instead of external CDN URLs. Keep static JS and generated CSS versioned when
they are part of the rendered UI.

The notification UI uses data attributes and delegated JavaScript actions. Avoid
adding inline `onclick` handlers to notification templates.

## Request Approval Rules

Employees can create and track their own leave and IOU requests. Approval is
limited to:

- superusers/admins
- users in the `HR` group
- users marked as managers
- users with `payroll.change_leaverequest` or `payroll.change_iou`

Do not treat generic Django `is_staff` as approval authority.
