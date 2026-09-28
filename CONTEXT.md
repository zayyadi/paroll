# Paroll

Multi-tenant Nigerian HR, payroll, accounting, and inventory workspace. One shared-schema database; every business row belongs to exactly one Company.

## Language

### Tenancy

**Company**:
The tenant workspace. The isolation boundary for all business data.
_Avoid_: tenant, organization, business, account

**CompanyMembership**:
A User's role (owner, admin, member) inside one Company.
_Avoid_: membership, team member, workspace user

**User**:
An authentication identity (email + password + OTP). Never an employee record.
_Avoid_: employee account, staff user

### People

**EmployeeProfile**:
The canonical employee record, scoped to one Company. The only object payroll, leave, attendance, and appraisal attach to.
_Avoid_: Employee, staff, profile, user

**Candidate**:
A pre-employment person in a hiring pipeline. Becomes an EmployeeProfile only on hire.
_Avoid_: applicant, prospect, employee (before hire)

**Department**:
An organizational grouping inside one Company.
_Avoid_: unit, team, division

### Payroll

**Payroll**:
An EmployeeProfile's annual salary configuration (basic, housing, transport, statutory flags). Not a pay run.
_Avoid_: salary config, payt, employee pay

**PayrollRun**:
One pay period for one Company, with lifecycle Draft → Calculated → Reviewed → Approved → Locked → Paid.
_Avoid_: PayRun, payday, pay period, payvar run

**PayrollEntry**:
One EmployeeProfile's variable inputs (allowances, deductions) for a period.
_Avoid_: payvar, payt, payroll line

**Payslip**:
The per-employee computed result for one PayrollRun. Read-only once locked.
_Avoid_: pay slip, salary slip

**SalaryHistory**:
An immutable record of an EmployeeProfile's Payroll change with effective date and approver.
_Avoid_: salary log, pay history

### Time

**LeaveRequest**:
An employee's request for time off under one LeavePolicy, resolved by manager then HR approval.
_Avoid_: time off, leave application, time-off request

**LeavePolicy**:
One Company's allowance rules for one leave type (annual, sick, casual, maternity, paternity), including carryover.
_Avoid_: leave rule, leave config

**LeaveBalance**:
An EmployeeProfile's remaining days per leave type per year, after carryover and deductions.
_Avoid_: leave days, leave quota

**AttendanceRecord**:
The fact of one EmployeeProfile's presence or absence on one work date. LeaveRequests populate these; they do not replace them.
_Avoid_: clock record, timesheet entry

### Money owed

**IOU**:
A loan or advance to one EmployeeProfile, repaid by salary deduction. Has tenor, status, and outstanding balance.
_Avoid_: loan, advance, salary advance (unless EWA)

**EWA Advance**:
An IOU with `is_ewa=True`: a single-cycle earned-wage advance capped by earned net, cycle limits, and take-home floor. Not a general loan.
_Avoid_: early salary, pay advance, EWA loan

**Deduction**:
A manual charge attached to a PayrollEntry (IOU installment, lateness, absence, damage, misc).
_Avoid_: penalty, charge

### Accounting

**Journal**:
A balanced double-entry document (debits equal credits) in one Company, with lifecycle Draft → Pending → Approved → Posted → Reversed.
_Avoid_: entry, transaction, voucher

**AccountingPeriod**:
One month inside a FiscalYear. Posting targets a period; closed periods reject new posts.
_Avoid_: period, month, paydays

**FiscalYear**:
One Company's financial year bounding its AccountingPeriods. Close requires all periods closed.
_Avoid_: financial year, FY, accounting year

**RemittanceRecord**:
Proof that one statutory obligation (PAYE, pension, NHF, NHIA, ITF, NSITF) was remitted for one period.
_Avoid_: remittance, statutory receipt, compliance record
