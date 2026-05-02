# Employee Management Expansion Plan

This plan turns the requested broad employee-management expansion into deliverable phases on top of the new workforce foundation models.

## Phase 1: Data Foundations

Completed in this pass:

- Attendance records
- Employee documents
- Asset categories and employee assets
- Workflow templates and executions
- Positions
- Skills and employee skills
- Goals
- One-on-ones
- Survey templates, questions, and responses
- Learning courses and enrollments
- Benefit plans and enrollments

Files:

- `payroll/models/workforce.py`
- `payroll/migrations/0047_surveyquestion_assetcategory_benefitplan_and_more.py`
- `payroll/admin/general_admin.py`

## Phase 2: Operational Workflows

- Attendance clock-in/clock-out views
- Who-is-out calendar
- Onboarding and offboarding workflow runner
- Policy acknowledgement flows
- Asset assignment and return workflows
- Benefit enrollment self-service
- Learning assignment automation

## Phase 3: Employee Experience

- Goals and check-in UI
- One-on-one scheduling and notes
- Pulse survey creation, distribution, and analytics
- Skills profile and internal mobility views
- Position directory and org chart

## Phase 4: Payroll and Compliance Intelligence

- Attendance-to-payroll linkage
- Benefits-to-payroll deductions linkage
- Mandatory training compliance alerts
- Document expiry reminders
- Workflow-driven probation and review milestones

## Phase 5: Automation and Reporting

- Workflow builder UI
- Survey dashboards
- Skills gap dashboards
- Asset lifecycle reporting
- Learning completion dashboards
- Benefits enrollment dashboards

## Delivery Notes

- Build tenant-scoped features only.
- Reuse existing notification and audit patterns.
- Prefer incremental vertical slices: model, admin, service, view, template, tests.
- Keep payroll-critical logic isolated from optional HR modules until explicitly integrated.
