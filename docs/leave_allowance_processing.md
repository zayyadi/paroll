# Automatic Leave Allowance Processing

When a leave request changes from `PENDING` to `APPROVED`, payroll now processes
the leave allowance automatically.

## Flow

1. `LeaveRequest.save()` detects the first approval.
2. `payroll.services.leave_allowance.process_leave_allowance_for_request()` calculates
   the allowance from `CompanyPayrollSetting.leave_allowance_percentage`.
3. An `Allowance` row is created with `allowance_type="LV"` and
   `source_leave_request` pointing to the approved leave request.
4. A posted accounting journal is created against that allowance:
   - Debit `Allowances Expense`
   - Credit `Cash and Cash Equivalents`
5. A `LeaveAllowanceEmailJob` row is created and queued after the database
   transaction commits.
6. Celery runs `payroll.send_leave_allowance_slip` on the
   `notifications_normal` queue.
7. The task renders `templates/pay/leave_allowance_slip_pdf.html`, attaches the
   generated PDF to `templates/email/leave_allowance_slip_email.html`, and emails
   the employee.

Employees can open the slip from `Leave Requests > Allowance Slip`, and can
download the PDF from that page.

## Idempotency

`Allowance.source_leave_request` and `LeaveAllowanceEmailJob.leave_request` are
one-to-one relationships. Saving an already approved leave request will not
create duplicate allowance rows or duplicate email jobs.

Payroll calculations still include the automatic leave allowance through the
normal allowance table. The older approved-leave fallback remains in place only
for historical approved leave requests that do not yet have a processed
allowance row.

## Operations

Run the worker with the notifications queue:

```bash
venv/bin/celery -A core worker -Q notifications_normal --loglevel=info
```

Monitor or retry failed leave allowance jobs from Django admin at
`Payroll > Leave allowance email jobs`, or from the shell by checking
`LeaveAllowanceEmailJob.status`. To resend one failed job:

```python
from payroll.models import LeaveAllowanceEmailJob

job = LeaveAllowanceEmailJob.objects.get(pk=1)
job.enqueue()
```

The task updates `queued`, `running`, `sent`, and `failed` states plus
`error_message`, `started_at`, and `completed_at`.

## Backfill Existing Approved Leaves

If a leave was approved before this workflow ran, process it with:

```bash
venv/bin/python manage.py process_leave_allowances --leave-id 104
```

Preview matching approved leave requests without writing:

```bash
venv/bin/python manage.py process_leave_allowances --dry-run
```
