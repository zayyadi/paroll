# HR Employee System Review (2026-02-26)

Legal note: this is an engineering/compliance readiness review, not legal advice. Final policy/legal interpretation should be validated by Nigerian-qualified counsel.

## Scope Reviewed
- Employee onboarding and profile management
- Leave policy and leave-request workflow
- IOU workflow and notifications
- Payroll settings that encode statutory percentages
- Disciplinary and appraisal touchpoints
- Employee-facing page design consistency

## Standards Baseline Used
- Nigeria Pension Reform Act baseline contribution ratios (employee 8%, employer 10%) via PenCom guidance.
- National Housing Fund (NHF) employee contribution baseline (2.5% of basic salary) via FMBN.
- Nigeria Data Protection Act / data minimization principles via NDPC.
- General international HR controls: documented workflow integrity, objective decision records, and auditable status transitions.

## Findings and Actions

### 1) Employee Contact Data Validation
- Finding: phone validators were in a US-centric pattern and rejected many valid Nigeria/international formats.
- Action taken:
  - Replaced model phone validators with an E.164-compatible + Nigeria-local validator.
  - Applied to `phone`, `emergency_contact_phone`, and `next_of_kin_phone`.

### 2) Leave Workflow Integrity
- Finding: leave requests did not block overlapping pending/approved requests for the same employee.
- Risk: duplicate approvals and inconsistent leave balance handling.
- Action taken:
  - Added overlap validation in `LeaveRequest.clean()` for date-range collisions against `PENDING` and `APPROVED` requests.

### 3) Payroll Compliance Guardrails (Nigeria-focused)
- Finding: `CompanyPayrollSetting` had field-level min/max validation but no cross-field or statutory-baseline checks.
- Action taken:
  - Added `clean()` rules to enforce:
    - `basic + housing + transport` > 0 and <= 100.
    - employee pension >= 8%.
    - employer pension >= 10%.
    - NHF >= 2.5%.
  - Normalized 13th-month config so if disabled, percentage is set to `0`.

### 4) Notification/Event Correctness
- Finding: rejected IOU events were emitted with `IOU_APPROVED` event type.
- Action taken:
  - Fixed event type to `IOU_REJECTED` for rejected IOU dispatch.

### 5) UI Uniformity and Quality
- Findings:
  - Employee templates were stylistically inconsistent.
  - `add_employee` only rendered form content when there were validation errors.
- Actions taken:
  - Rebuilt `add_employee`, `update_employee`, and `update_profile` pages to a unified `base_new` visual system (cards, spacing, actions).
  - Fixed `add_employee` to always render both account and profile forms.
  - Added consistent form widget classes in `EmployeeProfileForm` and `EmployeeProfileUpdateForm`.

## Feature-by-Feature Review Status
- Employee profile CRUD: reviewed and patched (validation + UI consistency).
- Leave lifecycle: reviewed and patched (overlap control).
- IOU lifecycle: reviewed and patched (event correctness).
- Payroll settings: reviewed and patched (Nigeria baseline guardrails).
- Appraisal workflow: reviewed for structure; no immediate blocking defect found in this pass.
- Disciplinary workflow: reviewed at integration level; deeper legal-process checks still recommended.
- Notifications: reviewed and partially patched (IOU rejected event type).

## Remaining High-Priority Follow-ups
- Add explicit policy/versioning metadata for leave and disciplinary templates.
- Introduce role-segregation checks for high-risk approvals (maker-checker pattern).
- Add consent/retention controls for sensitive employee data fields.
- Add DB-backed integration tests for leave overlap and payroll setting validations in CI.

## Engineering Validation
- `manage.py check`: passes.
- Migrations generated for updated model fields/validators.
- Full test run blocked in this environment by PostgreSQL connection availability.
