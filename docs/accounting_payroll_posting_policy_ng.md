# Nigeria Payroll Accounting Posting Policy

This policy defines the minimum posting standard for payroll accounting in this system, aligned to IFRS-style double-entry discipline and Nigerian statutory payroll components.

## 1. Core Principles
- Every payroll close must create a balanced journal (`total debits == total credits`).
- Employee deductions are recognized as liabilities until remitted to authorities or institutions.
- Employer statutory contributions are recognized as employer expense plus matching liability.
- Net salary paid is credited to cash/bank.
- Payroll journals should be posted once per payroll run to avoid duplication.

## 2. Payroll Close Posting Map
- `Salary Expense (6010)`:
  - `DEBIT` by `net pay + employee-side deductions/liabilities`.
- `Cash and Cash Equivalents (1010)`:
  - `CREDIT` by net pay.
- `PAYE Tax Payable (2110)`:
  - `CREDIT` by PAYE amount withheld.
- `Pension Payable (2120)`:
  - `CREDIT` by employee pension withheld.
  - `CREDIT` by employer pension contribution accrued.
- `NHF Payable (2150)`:
  - `CREDIT` by NHF amount withheld.
- `Health Contribution Payable (2130)`:
  - `CREDIT` by employee health contribution withheld.
  - `CREDIT` by employer health contribution accrued.
- `NSITF Expense (6040)`:
  - `DEBIT` by employer NSITF expense.
- `NSITF Payable (2140)`:
  - `CREDIT` by employer NSITF accrued liability.
- `Other Deductions Payable (2160)`:
  - `CREDIT` by approved non-IOU deductions.
- `Employee Advances (1400)`:
  - `DEBIT` when IOU is disbursed/approved.
  - `CREDIT` when IOU is recovered via payroll.

## 3. Timing and Cutoff
- Posting trigger: payroll run transition from open to `closed`.
- Deductions and allowances are recognized within the payroll month/year cutoff.
- IOU repayment is recognized during payroll close to match salary period (not at deduction record creation).

## 4. Controls
- Closed periods must reject new postings.
- Auto-posted system journals must still preserve audit metadata (`approved_at`, `posted_at`).
- Duplicate posting signals for the same business event must be disabled.

## 5. Operational Review Checklist
- Confirm payroll close journal is `POSTED`.
- Confirm journal is balanced.
- Confirm liability accounts reflect statutory and employee deductions.
- Confirm expense accounts reflect gross employment cost (employee + employer side).
- Reconcile `PAYE/Pension/NHF/Health/NSITF` liabilities with remittance reports before payment.

