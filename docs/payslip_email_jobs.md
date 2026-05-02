# Payslip Email Background Jobs

Payslip emails are sent outside the pay-period creation request. Creating a pay
period writes a `PayslipEmailJob`, then queues the Celery task
`payroll.send_payslips_for_payroll_run` on the `notifications_normal` queue after
the database transaction commits.

Each employee email includes a generated PDF payslip attachment. The attachment
is built from `templates/pay/payslip_pdf.html`, named like
`payslip_<employee-id>_<month>.pdf`, and sent with MIME type `application/pdf` so
employees can open or download the payslip directly from their email client.

## Required Services

Redis must be running locally:

```bash
redis-cli ping
```

Expected response:

```text
PONG
```

The Celery worker must be started from the repository root:

```bash
venv/bin/celery -A core worker -l INFO -Q notifications_critical,notifications_high,notifications_normal,notifications_low --concurrency=4
```

The Celery app loads `.env` through `core/celery.py`, so local worker startup uses
the same environment variables as `manage.py`.

## Health Checks

Confirm Celery can load Django and the broker settings:

```bash
venv/bin/celery -A core report
```

Confirm the worker is online:

```bash
venv/bin/celery -A core inspect ping
```

Check waiting jobs in local Redis DB 2:

```bash
redis-cli -n 2 LLEN notifications_normal
```

Inspect active/reserved/scheduled work:

```bash
venv/bin/celery -A core inspect active
venv/bin/celery -A core inspect reserved
venv/bin/celery -A core inspect scheduled
```

## Admin Workflow

Open Django admin and go to **Payslip email jobs**.

Useful filters:

- `queued`: job was created but has not completed.
- `running`: a worker started the job.
- `sent`: all payslip emails sent without skipped employees.
- `partial`: some employees were skipped; check `skipped_details`.
- `failed`: the task failed before completion; check `error_message`.

To resend a job:

- Click **Resend** on a single row, or
- Open the job detail and use the **Resend** link, or
- Select rows and run **Resend selected payslip email jobs**.

Resend requeues the existing job. It does not start or restart the Celery worker.

## Fallback Without Celery

If Celery cannot run but payslips must be sent, process queued or failed jobs
synchronously:

```bash
venv/bin/python manage.py process_payslip_email_jobs --status queued --status failed --limit 25
```

Process one job:

```bash
venv/bin/python manage.py process_payslip_email_jobs --job-id 123
```

This command sends emails in the current shell process and updates the same
`PayslipEmailJob` status fields.

## Troubleshooting

If tasks do not run:

1. Run `venv/bin/celery -A core report`. If this fails, fix `.env` or Django
   settings before testing email delivery.
2. Run `venv/bin/celery -A core inspect ping`. If no worker replies, start the
   worker command above.
3. Verify the worker command includes `notifications_normal`.
4. Check **Payslip email jobs** in admin. `queued` means no worker completed it;
   `failed` means the worker started but hit an exception.
5. Check worker logs for SMTP/PDF errors.
6. Use the synchronous fallback command for urgent resend while the worker issue
   is being fixed.
