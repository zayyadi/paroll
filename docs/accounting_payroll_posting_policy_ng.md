# Nigeria Payroll Accounting Posting Policy

This policy defines the minimum posting standard for payroll accounting in this system, aligned to IFRS-style double-entry discipline and Nigerian statutory payroll components.

## 1. Core Principles
- Every payroll journal must balance (`total debits == total credits`).
- Payroll is posted in three steps (accrual, salary payment, remittance), so the ledger shows at any time what is owed to staff and to each statutory body.
- Employee deductions are recognized as liabilities until remitted to authorities or institutions.
- Employer statutory contributions are recognized as employer expense plus matching liability.
- Cash/bank moves only when money actually leaves: at salary payment and at each remittance, never at payroll lock.
- Each system journal carries a `posting_key`, unique per company among journals still in effect, so a business event posts exactly once.

## 2. Accrual: posted when a payroll run is locked
Trigger: the independently approved `payroll.lock` action. Key: `payroll_run:<id>:accrual`. Amounts come from the figures frozen on each payroll entry.

- `Salaries and Wages Expense (6010)`: `DEBIT` gross pay (net pay + all employee deductions − allowances).
- `Allowances Expense (6015)`: `DEBIT` period allowances.
- `Pension Expense – Employer (6020)`: `DEBIT` employer pension.
- `Health Contribution Expense – Employer (6030)`: `DEBIT` employer health contribution.
- `NSITF Expense (6040)`: `DEBIT` employer NSITF.
- `ITF Levy Expense (6050)`: `DEBIT` one twelfth of the annual ITF levy (ITF-liable companies only).
- `Net Salaries Payable (2105)`: `CREDIT` net pay.
- `PAYE Tax Payable (2110)`: `CREDIT` PAYE withheld.
- `Pension Payable (2120)`: `CREDIT` employee pension withheld + employer pension.
- `Health Contribution Payable (2130)`: `CREDIT` employee + employer health contribution.
- `NSITF Payable (2140)`: `CREDIT` employer NSITF.
- `NHF Payable (2150)`: `CREDIT` NHF withheld.
- `Other Deductions Payable (2160)`: `CREDIT` approved non-IOU deductions.
- Water rate withheld is credited to `Other Deductions Payable (2160)`.
- `ITF Payable (2180)`: `CREDIT` ITF accrued.
- `Employee Advances (1400)`: `CREDIT` IOU recovered via payroll (`DEBIT` when the IOU is approved).

## 3. Salary payment
Trigger: confirming an independently approved bank payment file, which must cover the whole payroll. Key: `payroll_run:<id>:payment:bank_file:<file id>`.

- `Net Salaries Payable (2105)`: `DEBIT` amount paid.
- `Bank Accounts (1020)`: `CREDIT` amount paid.

Confirmation also moves the run to **Paid**. Runs locked before this policy (their accrual credited Cash directly) have nothing outstanding, so no payment journal is posted for them.

## 4. Statutory remittance
Trigger: marking an obligation remitted on the compliance calendar. Like any manual journal, it posts once an accountant independently approves it. Key: `remittance:<record id>`.

- `<body> Payable`: `DEBIT` exactly what that period's accrual journals credited to it (ITF: the whole year).
- `Bank Accounts (1020)`: `CREDIT` the same amount.

Undoing the remittance raises a reversal request; once approved, the payable reopens. Filing-only obligations (annual PAYE return) post nothing.

## 5. Timing and Cutoff
- Accrual date: first day of the payroll month. Payment and remittance: the day they are recorded.
- Deductions and allowances are recognized within the payroll month/year cutoff.
- IOU repayment is recognized at payroll lock to match the salary period (not at deduction record creation).

## 6. Controls
- Closed accounting periods reject new postings.
- A payroll run is locked only through the independent `payroll.lock` approval.
- Auto-posted system journals preserve audit metadata (`approved_at`, `posted_at`).
- Corrections are made by reversal, never by editing a posted journal.

## 7. Operational Review Checklist
- Confirm the payroll accrual journal is `POSTED` and balanced.
- Confirm Net Salaries Payable (2105) is zero for every Paid run.
- Confirm each statutory payable (2110–2180) equals the sum of periods not yet marked remitted.
- Confirm no remittance journal is left pending approval.
- Confirm expense accounts reflect gross employment cost (employee + employer side).
