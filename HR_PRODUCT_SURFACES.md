# HR product surfaces

The sidebar links to Timesheets, People analytics, Leave types and the new HR record lists. Links requiring model permissions appear for users holding those permissions. Every request is scoped to the user's selected company and requires membership; supplying a company ID cannot widen access.

- `people-analytics/`: dashboard and JSON download (`format=json`). Requires both employee-profile and payroll-entry view permissions because the dataset includes salary information. Optional `start` and `end` use ISO dates; `metrics` accepts comma-separated metric names. Invalid dates, inverted ranges and unknown metrics return validation errors.
- `timesheets/`: employees save their own weekly hours (blank hours seed from attendance), submit, withdraw and resubmit. Reviewers use independent approval stages. Editing is restricted to drafts/rejections. Withdrawal cancels the pending approval before reopening the draft.
- `settings/leave-types/`: authorised HR users create, edit and deactivate company leave types. Codes are immutable after creation. Entitlements are granted when an employee/year balance is first initialised, including custom types first used later in the year; changing the catalogue does not rewrite existing grants. New custom types, decimal balances and half-day usage use the leave ledger; fixed legacy balance columns remain available for older consumers.
- `hr-records/<resource>/`: paginated inspection for exit settlements, leave ledger, retro-pay deltas, compensation reviews and salary bands, with each model's view permission.

Under the existing `/api/v1/` mount:

| Resource | Operations |
| --- | --- |
| `people-analytics/` | GET, with the same filters and permissions as the dashboard |
| `timesheets/` | GET, POST (save own week); detail GET/PATCH |
| `timesheets/{id}/submit/` | POST |
| `timesheets/{id}/withdraw/` | POST |
| `timesheets/{id}/decide/` | POST with `decision` (`APPROVE` or `REJECT`) and `comment` (required for rejection) |
| `leave-types/` | GET/POST, detail GET/PUT/PATCH; deactivate with `is_active=false` |
| `leave-balances/` | GET own balances, optional `year` |
| `exit-settlements/`, `leave-ledger/`, `retro-pay-deltas/`, `comp-reviews/`, `salary-bands/` | GET list/detail with the corresponding model view permission |

All seven models are registered in Django admin. Leave types and salary bands can be edited with company-scoped model permissions. Workflow results and the append-only ledger are inspection-only; domain services and approval actions remain responsible for state changes.

Payroll settings expose **Require timesheet approval** and **Deduct unpaid absence**. When approval is required, the overtime allowance calculation only includes approved overtime whose date belongs to a payable timesheet week. Missing, draft, submitted and rejected weeks contribute zero overtime. When the setting is off, approved overtime follows the existing calculation. This applies to manual and attendance-generated overtime and uses the same Monday week boundary as preflight, including weeks crossing month boundaries. Fixed monthly salary and absence deductions retain their existing rules.

Apply migration `0088_productise_leave_catalogue` before using custom leave codes in requests and ledger entries. It removes the static five-code field choices; requests validate against the active company catalogue and ledger events validate against registered company types.

Default role setup (`payroll.permissions.setup_groups_and_permissions`) includes the new permissions for Admin/HR and timesheet review for Supervisor. Employee self-service needs no company-wide timesheet permission. Existing installations can assign these model permissions through Django's group editor, or refresh their default role setup using their existing provisioning process after migration.
