# Project Feature Guide

This guide documents the major features in the Payroll SaaS Platform, what each
feature does, and how users or operators are expected to use it. It is based on
the current Django apps, URL surfaces, models, and existing project docs.

## Product Overview

The project is a multi-tenant business operations platform built around payroll,
employee management, accounting, inventory, team standups, notifications, and a
tenant-scoped API. It uses a shared database and shared schema, with most
business records scoped by `company`.

Primary audiences:

- Company owners and administrators who manage tenant workspaces.
- HR/payroll teams who manage employees, payroll periods, leave, IOUs,
  performance, hiring, attendance, documents, benefits, and compliance reports.
- Accounting teams who manage charts of accounts, fiscal years, periods,
  journals, audit trails, financial reports, and payroll ledger postings.
- Inventory/operations teams who manage stock, suppliers, purchase orders,
  stock movements, invoices, returns, and inventory-accounting links.
- Employees who use self-service pages for profiles, payslips, leave, IOUs,
  documents, assets, learning, benefits, surveys, attendance, and chat.
- API clients that integrate with tenant-scoped payroll, HR, accounting,
  inventory, standup, and chat data.

## Core Concepts

### Tenancy

The system is tenant-scoped by company.

- `Company` represents a tenant workspace.
- `CompanyMembership` links users to companies with `owner`, `admin`, or
  `member` roles.
- `CustomUser.company` and `CustomUser.active_company` identify the user's
  default and current tenant context.
- `company.utils.get_user_company(user)` resolves the active company used by
  web views and API viewsets.
- `company.middleware.ActiveCompanyMiddleware` attaches
  `request.tenant_company` and can block authenticated non-superusers who have
  no company.
- `switch-company/<company_id>/` changes the active company for users who have
  memberships in multiple companies.

How to use:

1. Create a tenant with `python manage.py create_tenant "Company Name" owner@example.com --owner-password "..."`.
2. Log in as the owner user.
3. Use company switch controls or `/users/switch-company/<company_id>/` when
   the user belongs to more than one company.
4. Create operational data only after the correct active company is selected.

### Authentication And User Accounts

Users authenticate by email through the custom `users.CustomUser` model.

Features:

- Registration.
- Account activation by token.
- OTP sending and verification.
- Password reset and password change.
- Login and logout.
- Social login entry point.
- User settings.
- Company switching.

Main routes:

- `/users/register`
- `/users/login`
- `/users/logout`
- `/users/settings`
- `/users/password_reset/`
- `/users/password`
- `/users/send_otp/`
- `/users/verify_otp/`
- `/users/switch-company/<company_id>/`

How to use:

1. Register or create a user through admin/tenant command.
2. Activate the account if activation is enabled.
3. Log in with email and password.
4. Select the active company if the account has multiple memberships.

## Employee And HR Workspace

The employee and HR features live mostly in the `payroll` app. The name is
historical; the app now includes payroll, employee records, workforce features,
chat, notifications, requests, and employee self-service.

### Employee Home And Dashboard

The main authenticated app entry is `/app/`.

What it does:

- Shows the employee workspace.
- Surfaces payroll, request, company, notification, and self-service links.
- Uses active company context.

How to use:

1. Log in.
2. Open `/app/`.
3. Use the available links for employee self-service and HR tasks.

### Employee Profiles

Employee profiles are represented by `EmployeeProfile`.

What it stores:

- Company.
- Employee ID.
- Linked user account.
- Name and email.
- Department.
- Payroll configuration link.
- Rent relief data.
- Photo.
- NIN and TIN.
- Pension RSA and pension fund manager.
- HMO provider.
- Date of birth and employment.
- Contract type.
- Phone, gender, address.
- Emergency contact and next-of-kin.
- Job title.
- Bank and bank account details.
- Net pay.
- Employment status.

Important behavior:

- A profile is automatically created when a `CustomUser` is created.
- Saving an employee recalculates net pay from the linked payroll settings.
- Employee status controls eligibility for some payroll workflows.

Main routes:

- `/employee-profile/` updates the current employee's profile.
- `/employees/` lists employees.
- `/add_employee` creates an employee.
- `/employees/<id>/update/` edits an employee.
- `/delete_employee/<id>/` deletes an employee.
- `/profile/<user_id>/` views an employee profile.

How to use:

1. Create or invite a user.
2. Confirm the generated `EmployeeProfile`.
3. Assign department, payroll record, bank, pension, HMO, and contact details.
4. Keep employee status current. Terminated employees should not be selected for
   new payroll runs.

### Departments

Departments group employees within a company.

What they do:

- Organize employees.
- Scope positions and hiring.
- Feed employee filters in HR views and payroll selection views.

How to use:

1. Create departments through admin or employee management UI.
2. Assign employees to departments.
3. Use department filters in employee, payroll, attendance, and HR workflows.

### HR Dashboard

Route: `/hr-dashboard/`

What it does:

- Gives HR users a consolidated view of employee and request activity.
- Surfaces employee lists, payroll status, requests, and workforce workflows.

How to use:

1. Log in with HR/staff permissions.
2. Open `/hr-dashboard/`.
3. Review employee records, pending work, and operational summaries.

## Payroll

Payroll is built around `Payroll`, `PayrollEntry`, `PayrollRun`, and
`PayrollRunEntry`.

### Payroll Configuration

Company payroll settings are represented by `CompanyPayrollSetting` and
`CompanyHealthInsuranceTier`.

What settings control:

- Basic/housing/transport percentages.
- Employee and employer pension percentages.
- Health contribution settings and tiers.
- Leave allowance percentage.
- Thirteenth-month settings.

Routes:

- `/settings/payroll/`
- `/settings/payroll/edit/`

How to use:

1. Open payroll settings for the active company.
2. Configure statutory and company-specific contribution percentages.
3. Add health insurance tiers where needed.
4. Save settings before creating payroll records so calculations use the right
   values.

### Employee Payroll Records

`Payroll` stores employee compensation and derived payroll values.

What it calculates:

- Basic salary split.
- Housing.
- Transport.
- Gross income.
- Employee pension.
- Employer pension.
- Total pension.
- NHF.
- Employee health contribution.
- Employer health contribution.
- Total health/NHIF value.
- NSITF.
- Taxable income.
- PAYE.
- Water rate.

Route:

- `/add_pay`

How to use:

1. Create or update an employee.
2. Create a payroll record with the employee's basic salary.
3. Link the payroll record to the employee.
4. Review calculated values before adding the employee to a pay period.

### Payroll Variables

`PayrollEntry` represents an employee's payroll variable entry for payroll
processing.

What it does:

- Links an employee to a payroll-processing entry.
- Calculates allowances for the period.
- Calculates deductions for the period.
- Calculates IOU deductions for the period.
- Computes net pay for the entry.

Routes:

- `/varview/`
- `/varview/create-new/`
- `/varview/<paydays>/`
- `/varview/<paydays>/download/`

How to use:

1. Use `/varview/create-new/` to create payroll entries for selected employees.
2. Review the payroll variable list.
3. Download variable reports when needed.

### Payroll Runs / Pay Periods

`PayrollRun` represents a pay period. Employees are attached through
`PayrollRunEntry`.

What it does:

- Groups employee payroll entries by pay period.
- Tracks active/closed status.
- Can queue payslip email jobs.
- On closure, posts payroll to accounting through ledger journal creation.

Routes:

- `/pay-period/`
- `/pay-period/create/`
- `/pay-period/create-new/`
- `/pay-periods/<slug>/`
- `/pay-periods/<slug>/update/`
- `/pay-periods/<slug>/delete/`

How to use:

1. Open `/pay-period/create/` or `/pay-period/create-new/`.
2. Select the pay month.
3. Select eligible employees.
4. Save the pay period.
5. Review details under `/pay-periods/<slug>/`.
6. Close the period only after the payroll is correct.
7. After closure, confirm the generated accounting journal.

Operational notes:

- Closed payroll runs should not be edited.
- Closing a payroll run creates accounting entries for salary expense, net pay,
  employee liabilities, employer pension, employer health, NSITF, and IOU
  recovery.
- If a closed payroll period has no journal, check the accounting Unposted
  Events report.

### Payslips

Payslip features allow employees and authorized payroll users to view and
download payslips.

Routes:

- `/payslips/`
- `/payslip/<id>/`
- `/payslip/pdf/<id>/`
- `/list_payslip/<emp_slug>/`

What they do:

- List payslips.
- Show a payslip detail page.
- Generate PDF payslips.
- Restrict employee access so users cannot view other employees' payslips
  unless they have payroll permissions.

How to use:

1. Create a pay period with payroll entries.
2. Open the payslip list.
3. Select a payslip.
4. Download PDF if needed.

### Payslip Email Jobs

`PayslipEmailJob` tracks background delivery of payslips.

Statuses:

- Queued.
- Running.
- Sent.
- Partial.
- Failed.

What it does:

- Queues payslip email sending through Celery.
- Tracks sent/skipped counts.
- Stores skipped details and error messages.
- Allows admin monitoring and retry workflows.

How to use:

1. Start the Celery worker for notification queues.
2. Create a payroll run.
3. Confirm a payslip job is queued.
4. Monitor job status in Django admin.
5. Investigate skipped details for missing employee emails or PDF generation
   failures.

### Payroll Reports

Payroll report routes:

- `/bank`
- `/bank/<pay_id>/`
- `/bank/<pay_id>/download/`
- `/nhis`
- `/nhis/<pay_id>/`
- `/nhis/<pay_id>/download/`
- `/nhf`
- `/nhf/<pay_id>/`
- `/nhf/<pay_id>/download/`
- `/payee`
- `/payee/<pay_id>/`
- `/payee/<pay_id>/download/`
- `/pension`
- `/pension/<pay_id>/`
- `/pension/<pay_id>/download/`

What they do:

- Bank reports list employee payment details for a pay period.
- NHIS/NHIF reports summarize health contribution data.
- NHF reports summarize housing fund deductions.
- PAYE reports summarize tax deductions.
- Pension reports summarize pension fund manager, RSA, salary, and pension
  contribution data.
- Download routes export report data for operational submission or finance
  review.

How to use:

1. Create and review a payroll run.
2. Open the required statutory or bank report.
3. Select the pay period.
4. Review totals and employee rows.
5. Download the report where needed.

### Allowances And Deductions

`Allowance` and `Deduction` are employee-specific adjustments.

Routes:

- `/add_allowance/`
- `/edit_allowance/<id>/`
- `/delete-allowance`
- `/add_deduction/`

What they do:

- Allowances increase employee pay for the matching period.
- Deductions reduce employee pay for the matching period.
- Leave allowance can be generated from leave processing.
- IOU repayment deductions are handled separately through `IOUDeduction`.

How to use:

1. Create an allowance or deduction for an employee.
2. Ensure the created date falls within the intended payroll period.
3. Review payroll entries so net pay includes the adjustment.

## Leave Management

Leave features are built around `LeavePolicy`, `LeaveBalance`, `LeaveRequest`,
and `LeaveAuditLog`.

### Leave Policies

Route:

- `/leave-policies/`

What they do:

- Define leave types, annual entitlement, carryover rules, and company policy.
- Provide the rules used by leave request and balance calculations.

How to use:

1. Create or review leave policies for the active company.
2. Set entitlement days and behavior.
3. Use these policies when employees apply for leave.

### Leave Requests

Routes:

- `/apply-leave/`
- `/leave-requests/`
- `/manage-leave-requests/`
- `/approve-leave/<pk>/`
- `/reject-leave/<pk>/`
- `/edit-leave-request/<pk>/`
- `/delete-leave-request/<pk>/`
- `/view-leave-request/<pk>/`

What they do:

- Employees apply for leave.
- Managers/HR review, approve, or reject requests.
- Leave balances are checked and updated.
- Audit logs capture leave workflow events.

How to use:

1. Employee opens `/apply-leave/`.
2. Select leave type and dates.
3. Submit request.
4. HR/manager opens `/manage-leave-requests/`.
5. Approve or reject with the appropriate action.
6. Employee tracks status in `/leave-requests/`.

### Leave Allowance Slips

Routes:

- `/leave-allowance-slip/<pk>/`
- `/leave-allowance-slip/<pk>/pdf/`

What they do:

- Show leave allowance calculation and details.
- Generate leave allowance PDF.
- Use `LeaveAllowanceEmailJob` for background email delivery when enabled.

How to use:

1. Approve or process a leave request that creates an allowance.
2. Open the slip route.
3. Download PDF if needed.

## IOU / Salary Advance

IOU features are built around `IOU` and `IOUDeduction`.

What IOUs do:

- Let employees request salary advances.
- Track approval, rejection, payment method, tenor, interest rate, due date,
  outstanding amount, and repayments.
- Support salary deduction repayment and direct payment repayment.
- Post accounting journals on approval and direct payment.
- Recognize salary deduction repayments during payroll period closure.

Routes:

- `/request-iou/`
- `/approve-iou/<iou_id>/`
- `/iou/`
- `/iou/<pk>/`
- `/iou/<pk>/update/`
- `/iou/<pk>/delete/`
- `/iou/<pk>/payment-slip/`
- `/iou-history/`
- `/my-iou-tracker/`

How to use:

1. Employee opens `/request-iou/`.
2. Enter amount, tenor, reason, interest, and payment method.
3. Submit for approval.
4. Authorized HR/payroll user reviews and approves/rejects.
5. For salary deduction IOUs, deductions are generated when payroll entries are
   created for eligible periods.
6. For direct payment IOUs, marking as paid posts the repayment journal.
7. Employee tracks status and outstanding amount from `/my-iou-tracker/`.

## Accounting

The accounting app provides general ledger, fiscal calendars, journals, audit,
financial reports, and integration reports for payroll and inventory events.

### Accounting Dashboard

Route:

- `/accounting/`

What it does:

- Shows counts for draft, pending, and posted journals.
- Shows recent journals.
- Shows active periods.
- Indicates role flags such as auditor, accountant, and payroll processor.

How to use:

1. Log in with an accounting role.
2. Open `/accounting/`.
3. Use dashboard links to accounts, journals, periods, audit, and reports.

### Chart Of Accounts

`Account` is the chart-of-accounts model.

Fields:

- Company.
- Name.
- Account number.
- Type: asset, liability, equity, revenue, expense.
- Description.

Routes:

- `/accounting/accounts/`
- `/accounting/accounts/create/`
- `/accounting/accounts/<pk>/`
- `/accounting/accounts/opening-balances/import/`
- `/accounting/accounts/adjust-balance/`

What it does:

- Stores tenant-scoped ledger accounts.
- Computes account balance from posted journal entries.
- Enforces unique account names and numbers per company.
- Supports opening balance imports.
- Supports balance adjustment journals.

How to use:

1. Create accounts by company.
2. Import opening balances where needed.
3. Use adjustment form for controlled balance corrections.
4. Review account detail and activity reports.

### Fiscal Years And Accounting Periods

Models:

- `FiscalYear`.
- `AccountingPeriod`.

Routes:

- `/accounting/fiscal-years/`
- `/accounting/fiscal-years/<pk>/`
- `/accounting/periods/`
- `/accounting/periods/<pk>/`
- `/accounting/periods/<pk>/close/`

What they do:

- Define accounting years and periods.
- Prevent overlapping fiscal years or periods.
- Allow periods and fiscal years to close.
- Prevent journal reversals in closed periods.

How to use:

1. Create or let utility functions create fiscal year and monthly periods.
2. Keep one current active fiscal year.
3. Close periods after review.
4. Close fiscal year only after all periods are closed.

### Journals And Journal Entries

Models:

- `Journal`.
- `JournalEntry`.
- `TransactionNumber`.

Routes:

- `/accounting/journals/`
- `/accounting/journals/create/`
- `/accounting/journals/<pk>/`
- `/accounting/journals/<pk>/edit/`
- `/accounting/journals/<pk>/approve/`

What they do:

- Create balanced accounting journals.
- Store debit and credit lines.
- Manage draft, pending approval, approved, posted, cancelled, and reversed
  states.
- Generate transaction numbers.
- Link journals to source objects such as payroll runs and IOUs.
- Enforce account and journal company consistency.

How to use:

1. Accountant creates a draft journal.
2. Add at least one debit and one credit entry.
3. Submit for approval.
4. Approver reviews and approves/posts or cancels.
5. Posted journals become part of account balances and reports.

### Journal Reversals

Routes:

- `/accounting/journals/<pk>/reverse/`
- `/accounting/journals/<pk>/reversal/initiate/`
- `/accounting/journals/<pk>/reversal/confirm/`
- `/accounting/journals/<pk>/reversal/partial/`
- `/accounting/journals/<pk>/reversal/correction/`
- `/accounting/journals/<pk>/reversal/history/`
- `/accounting/journals/reversal/batch/`

What they do:

- Reverse posted journals.
- Partially reverse selected entries.
- Reverse and create correction journals.
- Batch reverse multiple journals.
- Keep reversal history.

How to use:

1. Open a posted journal.
2. Choose the reversal action.
3. Enter a reason.
4. Confirm reversal.
5. Review reversal history.

Rules:

- Only posted journals can be reversed.
- Already reversed journals cannot be reversed again.
- Journals in closed periods cannot be reversed.
- Reversal permissions are restricted.

### Accounting Audit Trail

Model:

- `AccountingAuditTrail`.

Routes:

- `/accounting/audit/`
- `/accounting/audit/<pk>/`

What it does:

- Logs accounting create, update, delete, approve, reject, post, reverse, close
  period, and close fiscal year actions.
- Captures user, timestamp, IP address, user agent, content object, changes,
  reason, approval metadata, and company where possible.

How to use:

1. Auditors open `/accounting/audit/`.
2. Filter/search records.
3. Open detail pages for evidence.
4. Use audit records during close, correction, and compliance review.

### Financial Report Designer

Models:

- `FinancialReportDefinition`.
- `FinancialReportLine`.

Routes:

- `/accounting/reports/designer/`
- `/accounting/reports/designer/new/`
- `/accounting/reports/designer/<pk>/`
- `/accounting/reports/designer/<pk>/lines/new/`

What it does:

- Defines reusable financial reports.
- Supports profit and loss, balance sheet, and custom reports.
- Defines report lines as headings, account sums, or formulas.
- Supports sign inversion and zero-display controls.

How to use:

1. Create a report definition.
2. Add lines with row codes.
3. Attach accounts for account-sum lines.
4. Use formulas for calculated rows.
5. Review report output.

### Accounting Reports

Routes:

- `/accounting/reports/`
- `/accounting/reports/trial-balance/`
- `/accounting/reports/account-activity/`
- `/accounting/reports/general-ledger/`
- `/accounting/reports/balance-sheet/`
- `/accounting/reports/income-statement/`
- `/accounting/reports/account-balance/`
- `/accounting/reports/unposted-events/`
- `/accounting/reports/export/`
- `/accounting/reports/trial-balance/pdf/`
- `/accounting/reports/account-activity/pdf/`

What they do:

- Trial balance shows debit/credit balances by account.
- Account activity shows entries and running balance for an account.
- General ledger reports posted entry activity.
- Balance sheet summarizes assets, liabilities, and equity.
- Income statement summarizes revenue and expense.
- Account balance reports balance as of a date.
- Unposted events lists source events that should have journals but do not.
- PDF routes export report output.

How to use:

1. Open the reports index.
2. Select report type and filters.
3. Use period or date filters where available.
4. Export PDF/CSV when required.
5. Use Unposted Events after payroll or inventory processing to verify ledger
   completeness.

### Payroll Accounting Integration

Payroll posts journals through payroll signal handlers when key events occur.

Events:

- Payroll period closes.
- IOU approved.
- IOU paid directly.

Accounts created/used include:

- Salaries and Wages Expense.
- Allowances Expense.
- Pension Expense.
- Health Contribution Expense.
- NSITF Expense.
- Cash and Cash Equivalents.
- Bank Accounts.
- Employee Advances.
- PAYE Tax Payable.
- Pension Payable.
- Health Contribution Payable.
- NSITF Payable.
- NHF Payable.
- Other Deductions Payable.
- Interest Income.

How to use:

1. Ensure chart of accounts exists or allow payroll posting helpers to create
   required payroll accounts.
2. Create and close payroll run.
3. Review generated journal in accounting.
4. Use reports to validate balances.
5. Use Unposted Events if a source event did not post.

## HR Disciplinary Workflow

The disciplinary workflow is currently implemented in `accounting` models/views
but exposed under payroll HR routes. It is tenant-scoped by company.

Models:

- `DisciplinaryCase`.
- `DisciplinaryEvidence`.
- `DisciplinarySanction`.
- `DisciplinaryAppeal`.

Routes:

- `/hr/disciplinary-system/`
- `/hr/disciplinary/cases/`
- `/hr/disciplinary/cases/new/`
- `/hr/disciplinary/cases/<pk>/`
- `/hr/disciplinary/cases/<pk>/edit/`
- `/hr/disciplinary/cases/<pk>/start-investigation/`
- `/hr/disciplinary/cases/<pk>/evidence/add/`
- `/hr/disciplinary/cases/<pk>/decision/`
- `/hr/disciplinary/cases/<pk>/sanction/add/`
- `/hr/disciplinary/cases/<pk>/appeal/add/`
- `/hr/disciplinary/appeals/<pk>/review/`

What it does:

- Records disciplinary cases.
- Assigns case numbers.
- Computes required review level from severity and risk flags.
- Tracks investigation, panel review, decision, appeal, close, and dismissal
  states.
- Stores evidence, sanctions, appeals, and outcome notes.
- Applies termination sanctions by disabling the user and marking the employee
  profile as terminated.

How to use:

1. Open `/hr/disciplinary-system/` to read the framework.
2. Create a case from `/hr/disciplinary/cases/new/`.
3. Select only respondents in the active company.
4. Add allegation details, severity, and risk flags.
5. Start investigation.
6. Add evidence.
7. Record decision and findings.
8. Add sanction where appropriate.
9. Allow appeal and review appeal outcome.
10. Close the case.

Access:

- Superusers.
- Auditors.
- Accountants.
- Payroll processors.
- HR users with employee profile view permission.

## Employee Performance And Development

### Appraisals And Reviews

Models:

- `Appraisal`.
- `AppraisalAssignment`.
- `Metric`.
- `Review`.
- `Rating`.

Routes:

- `/appraisals/`
- `/appraisals/create/`
- `/appraisals/<pk>/`
- `/appraisals/<pk>/update/`
- `/appraisals/<pk>/delete/`
- `/appraisals/assign/`
- `/appraisals/<appraisal_pk>/employees/<employee_pk>/reviews/create/`
- `/reviews/<pk>/`
- `/reviews/<pk>/update/`
- `/reviews/<pk>/delete/`

What it does:

- Defines appraisal periods.
- Assigns appraisers and appraisees.
- Captures reviews and metric ratings.
- Supports employee and manager performance workflows.

How to use:

1. Create an appraisal period.
2. Assign appraisers and appraisees.
3. Create reviews for assigned employees.
4. Rate metrics and add comments.
5. Review appraisal details.

### Goals And One-On-Ones

Models:

- `Goal`.
- `OneOnOne`.

Routes:

- `/performance/`
- `/performance/overview/`
- `/performance/one-on-ones/<meeting_id>/complete/`

What it does:

- Tracks employee goals.
- Tracks manager/employee one-on-one meetings.
- Allows completion of one-on-one records.

How to use:

1. Employee opens `/performance/`.
2. HR/manager opens `/performance/overview/`.
3. Complete meetings when discussion is done.

## Workforce Management

### Hiring

Models:

- `Position`.
- `HiringStage`.
- `JobRequisition`.
- `HiringCandidate`.
- `HiringStageScorecard`.
- `JobOffer`.

Routes:

- `/hiring/`
- `/hiring/requisitions/create/`
- `/hiring/candidates/create/`
- `/hiring/candidates/<candidate_id>/scorecards/create/`
- `/hiring/candidates/<candidate_id>/advance/`
- `/hiring/candidates/<candidate_id>/offers/create/`
- `/hiring/offers/<offer_id>/accept/`

What it does:

- Defines positions and requisitions.
- Tracks candidates through hiring stages.
- Captures interviewer scorecards.
- Advances candidates.
- Creates and accepts job offers.
- Can create standard hiring stages for a company.

How to use:

1. Open `/hiring/`.
2. Create positions and requisitions.
3. Add candidates.
4. Score candidate stages.
5. Advance candidate to the next stage.
6. Create job offer.
7. Accept job offer.

### Skills

Models:

- `Skill`.
- `EmployeeSkill`.

What it does:

- Defines tenant-specific skills.
- Links skills to employees.
- Stores proficiency/employee skill metadata.

How to use:

1. Create skills.
2. Attach skills to employee profiles.
3. Use skill data for workforce planning and employee development.

### Attendance

Model:

- `AttendanceRecord`.

Routes:

- `/attendance/my-day/`
- `/attendance/clock/`
- `/attendance/`
- `/attendance/who-is-out/`

What it does:

- Tracks employee clock-in/clock-out records.
- Shows the current employee's attendance day.
- Provides HR attendance overview.
- Shows who is out.

How to use:

1. Employee opens `/attendance/my-day/`.
2. Use clock action to clock in or out.
3. HR opens `/attendance/` for overview.
4. Use `/attendance/who-is-out/` to see absence/out-of-office context.

### Documents

Model:

- `EmployeeDocument`.

Routes:

- `/documents/`
- `/documents/<document_id>/acknowledge/`
- `/documents/overview/`

What it does:

- Stores employee documents.
- Allows employee acknowledgment.
- Gives HR an overview of document assignments and acknowledgments.

How to use:

1. HR uploads/assigns documents.
2. Employee opens `/documents/`.
3. Employee acknowledges required documents.
4. HR reviews `/documents/overview/`.

### Assets

Models:

- `AssetCategory`.
- `EmployeeAsset`.

Routes:

- `/assets/`
- `/assets/overview/`
- `/assets/<asset_id>/return/`

What it does:

- Tracks assets assigned to employees.
- Allows employee-visible asset list.
- Tracks returns.

How to use:

1. HR/operations creates asset categories and assignments.
2. Employee views assigned assets.
3. Mark assets returned when handed back.

### Workflow Templates And Executions

Models:

- `WorkflowTemplate`.
- `WorkflowExecution`.

Route:

- `/workflows/`

What it does:

- Defines reusable HR/workforce workflows.
- Starts workflow executions for employees.
- Tracks workflow status and metadata.

How to use:

1. Create workflow templates.
2. Start workflows for employees.
3. Track execution status from `/workflows/`.

### Surveys

Models:

- `SurveyTemplate`.
- `SurveyQuestion`.
- `SurveyResponse`.

Routes:

- `/surveys/`
- `/surveys/<survey_id>/submit/`
- `/surveys/overview/`

What it does:

- Defines employee surveys.
- Captures survey answers.
- Gives HR an overview of responses.

How to use:

1. Create survey templates and questions.
2. Employee opens `/surveys/`.
3. Submit response.
4. HR reviews `/surveys/overview/`.

### Learning

Models:

- `LearningCourse`.
- `CourseEnrollment`.

Routes:

- `/learning/`
- `/learning/<enrollment_id>/complete/`
- `/learning/overview/`

What it does:

- Defines learning courses.
- Enrolls employees.
- Tracks completion.

How to use:

1. Create courses.
2. Enroll employees.
3. Employee opens `/learning/`.
4. Mark completed when done.
5. HR reviews `/learning/overview/`.

### Benefits

Models:

- `BenefitPlan`.
- `BenefitEnrollment`.

Routes:

- `/benefits/`
- `/benefits/<plan_id>/enroll/`
- `/benefits/overview/`

What it does:

- Defines benefit plans.
- Allows employee enrollment.
- Tracks benefit enrollment status.

How to use:

1. Create benefit plans.
2. Employee opens `/benefits/`.
3. Enroll in eligible plans.
4. HR reviews `/benefits/overview/`.

## Company Chat

Models:

- `CompanyChatRoom`.
- `CompanyChatMessage`.
- `CompanyChatReadState`.
- `CompanyChatRoomMember`.

Routes:

- `/chat/`
- API routes under `/api/v1/company-chat/rooms/`.
- API routes under `/api/v1/company-chat/messages/`.

What it does:

- Provides company-wide and room/direct chat.
- Tracks read state.
- Tracks room members and roles.
- Supports employee-to-employee direct rooms through API helpers.

How to use:

1. Open `/chat/`.
2. Send messages in company room or room/direct context.
3. API clients can create rooms, list messages, send messages, and mark read
   state through the chat API.

## Notifications

Models:

- `Notification`.
- `NotificationPreference`.
- `NotificationTypePreference`.
- `NotificationDeliveryLog`.
- `ArchivedNotification`.
- `NotificationTemplate`.

Routes:

- `/notifications/`
- `/notifications/enhanced/`
- `/notifications/dropdown/`
- `/notifications/<uuid>/`
- `/notifications/<uuid>/mark-read/`
- `/notifications/<uuid>/mark-unread/`
- `/notifications/<uuid>/delete/`
- `/notifications/mark-all-read/`
- `/notifications/delete-all-read/`
- `/notifications/count/`
- `/notifications/preferences/`
- `/notifications/preferences/<notification_type>/`
- `/notifications/aggregated/`
- `/notifications/<uuid>/expand/`
- `/notifications/digests/`
- `/notifications/digests/settings/`
- `/notifications/digests/<uuid>/`
- `/notifications/digest/enable-daily/`
- `/notifications/digest/enable-weekly/`
- `/notifications/digest/disable/`
- `/notifications/digest/trigger/`

What it does:

- Sends and displays in-app notifications.
- Supports email/SMS/push/channel preferences.
- Tracks delivery logs.
- Aggregates related notifications.
- Supports daily and weekly digests.
- Archives old notifications.

How to use:

1. Open notification list or dropdown.
2. Mark individual or all notifications as read.
3. Delete notifications when no longer needed.
4. Configure global preferences.
5. Configure type-specific preferences.
6. Enable daily or weekly digest.
7. Trigger manual digest for testing/operations.

Operational notes:

- Celery workers process notification delivery.
- Notification queues use priorities such as critical, high, normal, and low.
- See `docs/notification_system.md` for deeper architecture notes.

## Inventory

Inventory is tenant-scoped and integrates with accounting through posting
accounts and generated stock/financial events.

### Inventory Dashboard

Route:

- `/inventory/`

What it does:

- Shows inventory summary and navigation.
- Surfaces items, stock, purchases, documents, and operational actions.

How to use:

1. Open `/inventory/`.
2. Review counts, stock status, and action links.

### Posting Account Setup

Route:

- `/inventory/posting-accounts/`

What it does:

- Links inventory categories/items/workflows to accounting accounts.
- Ensures inventory transactions post to the correct accounts.

How to use:

1. Create accounting accounts first.
2. Open posting account setup.
3. Map inventory accounts such as inventory asset, COGS, revenue, tax, payables,
   receivables, or adjustment accounts.
4. Save before processing financial inventory transactions.

### Units Of Measure

Model:

- `UnitOfMeasure`.

Route:

- `/inventory/units/new/`

What it does:

- Defines quantity units such as pieces, cartons, kilograms, liters, or packs.

How to use:

1. Create units before creating items.
2. Select unit of measure on inventory items and transaction lines.

### Categories

Model:

- `InventoryCategory`.

Routes:

- `/inventory/categories/`
- `/inventory/categories/new/`

What it does:

- Groups inventory items.
- Stores accounting defaults and costing behavior where configured.
- Helps with search, reporting, and posting setup.

How to use:

1. Create category.
2. Assign items to category.
3. Configure posting accounts if applicable.

### Items

Model:

- `InventoryItem`.

Routes:

- `/inventory/items/`
- `/inventory/items/new/`
- `/inventory/items/<pk>/`

What it does:

- Stores SKU/item master data.
- Tracks category, unit, inventory settings, and stock data.
- Links to stock movements and valuation layers.

How to use:

1. Create units and categories.
2. Create an item with SKU and details.
3. Review item detail for stock movement history and stock status.

### Warehouses And Locations

Models:

- `Warehouse`.
- `StockLocation`.

Routes:

- `/inventory/warehouses/`
- `/inventory/warehouses/new/`
- `/inventory/locations/new/`

What they do:

- Define physical or logical storage warehouses.
- Define stock locations inside warehouses.
- Scope stock movements and transfers.

How to use:

1. Create warehouse.
2. Create locations inside warehouse.
3. Use locations for stock receipts, transfers, adjustments, and counts.

### Suppliers And Customers

Models:

- `Supplier`.
- `Customer`.

Routes:

- `/inventory/suppliers/`
- `/inventory/suppliers/new/`
- `/inventory/customers/`
- `/inventory/customers/new/`

What they do:

- Store supplier and customer master data.
- Support purchase orders, receipts, supplier returns, sales invoices, customer
  returns, and payments.

How to use:

1. Create suppliers for purchasing.
2. Create customers for sales.
3. Use supplier/customer records in inventory documents and payments.

### Purchase Orders

Models:

- `PurchaseOrder`.
- `PurchaseOrderLine`.

Routes:

- `/inventory/purchase-orders/`
- `/inventory/purchase-orders/new/`
- `/inventory/purchase-orders/<pk>/receive/`

What they do:

- Records intended purchases from suppliers.
- Stores line items, quantities, and costs.
- Tracks ordering and receiving.

How to use:

1. Create supplier and item records.
2. Create purchase order.
3. Add line items.
4. Receive purchase order when goods arrive.
5. Review resulting stock movements and documents.

### Inventory Documents And Stock Movements

Models:

- `InventoryDocument`.
- `StockMovement`.

Routes:

- `/inventory/documents/`
- `/inventory/movements/`

What they do:

- Inventory documents represent operational source documents.
- Stock movements record quantity movement in or out of locations.
- Movements are used by stock reporting and valuation.

How to use:

1. Process an inventory action such as receipt, sale, return, adjustment, or
   transfer.
2. Review generated document.
3. Review generated stock movements.

### Opening Stock

Route:

- `/inventory/opening-stock/`

What it does:

- Creates initial stock quantities and value.
- Establishes starting inventory balance for a company.

How to use:

1. Configure items, warehouses, and locations.
2. Enter opening quantities and cost.
3. Submit opening stock.
4. Verify movements and accounting impact where configured.

### Purchase Receipts

Models:

- `PurchaseReceipt`.
- `PurchaseReceiptLine`.

Route:

- `/inventory/purchase-receipts/new/`

What it does:

- Records received goods.
- Increases stock.
- Can create accounting entries for inventory and supplier payable depending on
  setup.

How to use:

1. Select supplier and warehouse/location.
2. Add items and quantities.
3. Submit receipt.
4. Verify stock movements.

### Sales Invoices

Models:

- `SalesInvoice`.
- `SalesInvoiceLine`.

Route:

- `/inventory/sales-invoices/new/`

What it does:

- Records customer sales.
- Reduces stock.
- Can post revenue, receivable/cash, tax, and COGS depending on setup.

How to use:

1. Select customer.
2. Add sold items and quantities.
3. Submit invoice.
4. Review stock movement and accounting entries.

### Returns

Models:

- `CustomerReturn`.
- `CustomerReturnLine`.
- `SupplierReturn`.
- `SupplierReturnLine`.

Routes:

- `/inventory/customer-returns/new/`
- `/inventory/supplier-returns/new/`

What they do:

- Customer returns increase stock or reverse a sale.
- Supplier returns decrease stock or reverse a purchase.

How to use:

1. Select customer or supplier.
2. Select item and quantity.
3. Submit return.
4. Verify stock and financial impact.

### Payments And Tax Remittance

Models:

- `CustomerPayment`.
- `SupplierPayment`.
- `TaxRemittance`.

Routes:

- `/inventory/customer-payments/new/`
- `/inventory/supplier-payments/new/`
- `/inventory/tax-remittances/new/`

What they do:

- Record customer receipts.
- Record supplier payments.
- Record tax remittances.
- Can create accounting journals where posting accounts are configured.

How to use:

1. Select relevant party.
2. Enter amount, date, and payment details.
3. Submit.
4. Review generated document/journal.

### Adjustments And Transfers

Routes:

- `/inventory/adjustments/new/`
- `/inventory/transfers/new/`

What they do:

- Adjustments correct stock quantities for shrinkage, damage, count
  corrections, or other operational reasons.
- Transfers move stock between locations.

How to use:

1. Select item and location.
2. Enter quantity and reason.
3. Submit adjustment or transfer.
4. Verify stock movements.

### Valuation And Stock Counts

Models:

- `InventoryValuationLayer`.
- `StockCount`.
- `StockCountLine`.

What they do:

- Valuation layers track item cost/value basis.
- Stock counts support physical count workflows.
- Stock count lines capture counted quantities for individual items.

How to use:

1. Use receiving/opening-stock actions to establish valuation layers.
2. Run stock count workflows when available.
3. Review discrepancies and post adjustments where needed.

## Standups

The standup module supports async team check-ins.

Models:

- `StandupTeam`.
- `StandupTeamMember`.
- `StandupQuestion`.
- `StandupCheckin`.
- `StandupAnswer`.
- `StandupDispatchLog`.
- `StandupFollow`.

Routes:

- Web dashboard: `/standup/`
- API routes under `/api/v1/standup-teams/`
- API routes under `/api/v1/standup-team-members/`
- API routes under `/api/v1/standup-questions/`
- API routes under `/api/v1/standup-checkins/`
- API routes under `/api/v1/standup-follows/`

What it does:

- Defines standup teams with cadence and time zone.
- Assigns employee members.
- Defines questions.
- Captures daily or periodic check-ins.
- Tracks blockers.
- Records reminders, missed check-ins, and digest dispatches.
- Supports follow-up actions.

How to use:

1. Create a standup team for the active company.
2. Add employee members.
3. Add active questions.
4. Employees submit check-ins.
5. Team leads review submitted/missed check-ins and blockers.
6. Use follow-up endpoints for action items.

## REST API

The API is versioned under `/api/v1/` and uses Django REST Framework.

Documentation routes:

- `/api/v1/schema/`
- `/api/v1/docs/swagger/`
- `/api/v1/docs/redoc/`

Authentication routes:

- `/api/v1/auth/token/`
- `/api/v1/auth/token/refresh/`
- `/api/v1/auth/context/`
- `/api/v1/auth/companies/`
- `/api/v1/auth/switch-company/`

Resource groups:

- Company chat rooms and messages.
- Departments.
- Employees.
- Payrolls.
- Payroll entries.
- Payroll runs.
- Payroll run entries.
- Leave policies.
- Leave requests.
- IOUs.
- Accounts.
- Fiscal years.
- Accounting periods.
- Journals.
- Journal entries.
- Inventory units.
- Inventory categories.
- Inventory items.
- Warehouses.
- Stock locations.
- Suppliers.
- Customers.
- Purchase orders.
- Inventory documents.
- Stock movements.
- Standup teams.
- Standup members.
- Standup questions.
- Standup check-ins.
- Standup follows.

How to use:

1. Obtain a JWT token from `/api/v1/auth/token/`.
2. Send `Authorization: Bearer <token>` on API requests.
3. Call `/api/v1/auth/context/` to see the active user/company context.
4. Use `/api/v1/auth/companies/` to list accessible companies.
5. Use `/api/v1/auth/switch-company/` to change active company.
6. Access resources through the router endpoints.

Tenant behavior:

- Most API viewsets inherit tenant scoping.
- Company is resolved from the authenticated user's active company.
- Some accounting APIs can be gated to superusers when the hardening flag is
  enabled.

## Public Marketing Site

Routes:

- `/` through the marketing app where configured.
- `/pricing/`
- `/about/`
- `/support/`
- `/security/`
- `/contact/`
- `/legal/privacy/`
- `/legal/terms/`
- `/legal/cookies/`

What it does:

- Provides public product, pricing, support, security, contact, privacy, terms,
  and cookie pages.

How to use:

1. Open the public site routes without authentication.
2. Use contact/support pages for inbound interest or help.

## Administration And Operations

### Django Admin

What it does:

- Provides admin access to users, companies, payroll records, accounting data,
  inventory data, notifications, jobs, and other models registered in admin
  modules.

How to use:

1. Create a superuser.
2. Open `/admin/`.
3. Use admin for setup, correction, and operational oversight.

### Management Commands

Known command areas:

- `create_tenant` creates company workspace and owner membership.
- Accounting commands create fake/sample accounting data, initial accounts,
  permissions, audit management, cash migration, and payroll statutory backfill.
- Payroll fake-data commands support local/test data generation.

How to use:

1. Run `python manage.py help` to list commands.
2. Read command README files in `accounting/management/commands/` and
   `payroll/management/commands/`.
3. Run commands in staging before production.

### Celery And Background Jobs

Used for:

- Payslip email delivery.
- Leave allowance slip delivery.
- Notification delivery.
- Notification archive/digest jobs.

How to use:

1. Start Redis.
2. Start Celery worker:
   `venv/bin/celery -A core worker -l INFO -Q notifications_critical,notifications_high,notifications_normal,notifications_low --concurrency=4`
3. Start Celery beat where scheduled jobs are required.
4. Monitor job models and Celery logs.

### Channels / WebSockets

The project includes Channels and Redis configuration for real-time features.

How to use:

1. Start the normal Django app.
2. Start Daphne for ASGI:
   `venv/bin/python -m daphne -b 0.0.0.0 -p 8001 core.asgi:application`
3. Ensure Redis is reachable.
4. Use WebSocket-enabled notification/chat surfaces where configured.

## Permissions And Access Control

Common access patterns:

- Login is required for internal app routes.
- Django permissions guard payroll, employee, accounting, and report actions.
- Accounting roles include Auditor, Accountant, and Payroll Processor.
- HR access can be granted through employee profile permissions and HR group
  membership.
- Tenant middleware ensures authenticated users operate inside an active
  company.
- Object queries generally filter by active company.

Recommended setup:

1. Create groups for HR, Accountant, Auditor, Payroll Processor, and admins.
2. Assign Django model permissions per role.
3. Use tenant membership to restrict company access.
4. Test access with non-superuser accounts.

## Typical Workflows

### New Tenant Setup

1. Run `create_tenant`.
2. Log in as owner.
3. Create departments.
4. Add employees.
5. Configure payroll settings.
6. Create accounting chart of accounts.
7. Configure inventory posting accounts if inventory is used.
8. Configure leave policies, benefits, documents, and notifications.

### Monthly Payroll

1. Confirm employee profiles and payroll records.
2. Add allowances/deductions.
3. Create payroll variables.
4. Create pay period and select employees.
5. Review pay period.
6. Generate payroll reports.
7. Close payroll period.
8. Review posted journal.
9. Send/download payslips.

### Employee Leave

1. HR configures leave policies.
2. Employee applies for leave.
3. Manager/HR approves or rejects.
4. System updates leave balance.
5. Leave allowance slip is generated where applicable.

### IOU / Advance

1. Employee requests IOU.
2. HR/payroll approves or rejects.
3. Approval posts employee advance journal.
4. Salary deduction IOUs are recovered through payroll.
5. Direct payments post cash/advance/interest journal.

### Purchase To Stock

1. Configure supplier, item, warehouse, and posting accounts.
2. Create purchase order.
3. Receive goods.
4. Review stock movement.
5. Review accounting impact.

### Sale To Payment

1. Configure customer, item, stock, and posting accounts.
2. Create sales invoice.
3. Review stock reduction.
4. Record customer payment.
5. Review accounting reports.

### Accounting Close

1. Review journals and reports.
2. Resolve unposted events.
3. Close accounting period.
4. Close fiscal year after all periods are closed.

## Known Caveats

- The `payroll` app contains both payroll and broad HR/workforce features.
  Future cleanup may split these domains into separate apps.
- Disciplinary workflows are exposed as HR routes but still implemented in the
  accounting app.
- Some legacy accounting test suites have been replaced with skipped placeholders
  until rewritten for tenant-scoped accounting and the custom email-based user
  model.
- Full production release should include broader end-to-end regression tests for
  tenant isolation, payroll posting, inventory posting, permissions, and API
  access.

## Related Documentation

- `docs/repo_organization.md`
- `docs/notification_system.md`
- `docs/payslip_email_jobs.md`
- `docs/leave_allowance_processing.md`
- `docs/employee_request_workflows.md`
- `docs/accounting_payroll_posting_policy_ng.md`
- `docs/accounting_inventory_recommendations_2026-05-14.md`
- `docs/inventory_business_prd_2026-05-14.md`
- `docs/production_readiness.md`
