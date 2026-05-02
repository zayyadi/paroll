# Employee Request Workflows

Employees can submit and track their own operational requests without needing
Django model permissions. Approval and cross-employee management stay restricted
to HR, managers, staff admins, and superusers.

## Leave

- Employees use `GET/POST /apply-leave/` to submit leave requests.
- New leave requests are always tied to the logged-in employee profile for the
  user's active company.
- New requests start as `PENDING`.
- Employees use `/leave-requests/` to track their own leave applications.
- HR, managers, staff admins, and superusers can use `/manage-leave-requests/`
  to see pending company requests.
- Leave approval and rejection are POST-only:
  - `POST /approve-leave/<id>/`
  - `POST /reject-leave/<id>/`
- Ordinary employees cannot approve or reject requests.
- Employees can edit or delete only their own pending leave requests.

## IOU

- Employees use `GET/POST /request-iou/` to submit IOU requests.
- New IOUs are always tied to the logged-in employee profile for the user's
  active company.
- New IOUs start as `PENDING`.
- Employees use `/iou-history/` or `/my-iou-tracker/` to track their own IOUs.
- HR, managers, staff admins, and superusers can review company IOUs.
- IOU approval remains restricted to HR, managers, staff admins, and superusers
  through `/approve-iou/<id>/`.
- Ordinary employees cannot approve IOUs.
- Employees can update or delete only their own pending IOUs.

## Permission Boundary

Request management is centralized in `_can_manage_employee_requests()` in
`payroll.views.payroll_view`.

That helper currently grants reviewer access to:

- superusers
- staff users
- users with `is_manager=True`
- users with `payroll.change_leaverequest`
- users with `payroll.change_iou`

Do not use `payroll.add_leaverequest` or `payroll.add_iou` to gate employee
self-service creation. Those permissions are for administrative model access,
not employee request submission.

## Verification

Run the focused request workflow tests:

```bash
venv/bin/python manage.py test payroll.tests_employee_requests --settings=core.settings_test
```

Run the broader route smoke coverage touched by these flows:

```bash
venv/bin/python manage.py test payroll.tests.EmployeeLeaveIOUTemplateSmokeTests payroll.tests.EmployeeLeaveIOUUrlWalkSmokeTests payroll.test_views --settings=core.settings_test
```
