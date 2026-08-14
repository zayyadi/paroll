# Phase 0 — Tenant-Scoping Audit (accounting + payroll)

Status: **audit complete (no code changes from this pass).** Companion to
`plans/TENANT_ISOLATION_ACCEPTANCE_MATRIX.md`. This is the inventory the
lockdown (`ACCOUNTING_SUPERUSER_ONLY_UNTIL_TENANT_SCOPED`) removal and the
`TENANT_SCOPING_ENFORCED` flip are gated on.

## 1. Method

- Model inventory: Django shell over every `accounting` and `payroll` model,
  classified by direct `company` FK presence.
- Queryset audit: AST scan of **160 files** (`accounting/`, `payroll/`,
  `api/v1/`) excluding migrations/tests — every `<Model>.objects.<method>()`
  and `get_object_or_404(<Model>)` call was checked for a company-scoping
  argument (`company=` or any `*__company=`); plus grep passes over CBV
  `get_queryset` definitions, forms' declared querysets, and spot reads.
- Blind spots acknowledged: variable-held querysets filtered in later
  statements and related-manager chains (`period.journals.all()`) are
  parent-scoped by construction and not flagged; form defaults are unscoped
  unless the view passes `company` (verified: accounting views do).

## 2. The lockdown and who is inside it

`ACCOUNTING_SUPERUSER_ONLY_UNTIL_TENANT_SCOPED` (prod default **on**) blocks
non-superuser, non-finance users from accounting pages (`accounting/mixins.py`
+ `decorators.py`). **Finance users and superusers bypass it today** — so the
two confirmed cross-tenant leaks below are live for finance users **right
now**, and for everyone once the lockdown comes off.

## 3. Queryset findings (missing company filter)

### 🔴 Confirmed cross-tenant leaks — fix before lockdown removal

| # | Location | Model | Problem |
|---|---|---|---|
| A1 | `accounting/views.py` `AuditTrailListView.get_queryset` (~L1325) | `AccountingAuditTrail` (has company FK) | `AccountingAuditTrail.objects.all()` — **no company filter**. Auditors/finance see every company's audit trail (users, IPs, actions). Fix: `filter(company=get_user_company(request.user))` |
| A2 | `payroll/views/payroll_audit.py` `audit_trail_list` (L25) + `audit_trail_detail` (L95) | `AuditTrail` (payroll, **no** company FK) | `AuditTrail.objects.all()` + `get_object_or_404(AuditTrail, pk=...)` — **no company and no ownership filter**; any `view_audittrail` holder sees all companies' logs. Fix requires the company FK (table P2 below), then scoping |

### 🟡 Verify before flip (likely safe, defaults are unscoped)

| # | Location | Notes |
|---|---|---|
| B1 | `accounting/forms.py` L313/338/368/408/426/597 | Declared `queryset=Model.objects.all()` — scoped in `__init__` **only when `company=` is passed**. Views pass it today; assert no instantiation path omits it (a missing company kwarg would silently show all companies' options) |
| B2 | `accounting/views.py` `AccountingPeriodCloseView` L1284/1291/1297 | `get_object_or_404(AccountingPeriod, pk=...)` in `get_context_data`/`post` are unscoped, but `PeriodClosingMixin` (via `TenantScopedPermissionObjectMixin`) authorizes the object at dispatch — **not exploitable**, but replace the redundant unscoped lookups with `self.get_permission_object()` |
| B3 | `payroll/admin/general_admin.py` L534/624 | Admin resend-email actions fetch `PayslipEmailJob`/`LeaveAllowanceEmailJob` by pk — admin-gated (staff/superuser); note for post-flip admin review |

### ✅ Verified scoped (not findings)

- **Accounting CBVs** — all `get_queryset` overrides filter by
  `company=get_user_company(...)`: Account, FinancialReportDefinition,
  Journal, FiscalYear, AccountingPeriod, AccountReconciliation,
  DisciplinaryAppeal (`case__company=...`), DisciplinaryCase via
  `_disciplinary_case_queryset_for_user`.
- **api/v1 viewsets** — `TenantScopedModelViewSet` base filters via
  `company_filter_path`; chat message/room viewsets and `StockMovement`
  scope by company; `JournalViewSet` uses the base (`company_filter_path="company"`).
- **payroll views** — every function view resolves
  `company = get_user_company(request.user)`; `visible_employee_profiles_for`
  is company-scoped; appraisal/IOU/notification CBVs scope by company or
  recipient identity.
- **Notification lookups** (5 `get_object_or_404(Notification, id=..., recipient=...)`)
  are scoped by the recipient's employee identity (user-level) — correct.
- **Child-model direct queries** (`JournalEntry`, `BudgetLine`, etc.) always
  carry parent-scoping kwargs when queried directly; most access is via
  parent related managers.

## 4. Tables needing a nullable `company` FK + backfill

Rule: the table is tenant data, lacks a direct `company` FK, and is either
queried directly today or must be directly scoped for
`TENANT_SCOPING_ENFORCED`. Backfill source is the parent chain.

### Accounting — 11 tables (required before the lockdown comes off)

| Table | Backfill via |
|---|---|
| `JournalEntry` | `journal.company` |
| `BudgetLine` | `budget.company` |
| `TaxReturnLine` | `tax_return.company` |
| `CurrencyRevaluationLine` | `revaluation.company` |
| `ReconciliationItem` | `reconciliation.company` |
| `FinancialReportLine` | `report.company` |
| `TransactionNumber` | `fiscal_year.company` |
| `DisciplinaryCaseAudit` | `case.company` |
| `DisciplinaryEvidence` | `case.company` |
| `DisciplinarySanction` | `case.company` |
| `DisciplinaryAppeal` | `case.company` |

### Payroll — 29 tables (required before `TENANT_SCOPING_ENFORCED` flips on)

| Group | Tables | Backfill via |
|---|---|---|
| Employee-scoped (14) | `SalaryHistory`, `Allowance`, `Deduction`, `IOU`, `IOUDeduction` (via `iou`), `LeaveBalance`, `LeaveCarryover`, `LeaveRequest`, `LeaveAuditLog`, `LeaveApproval`, `Notification`, `NotificationPreference`, `NotificationDeliveryLog`, `ArchivedNotification` | `employee.company` (via the employee/user FK) |
| Run-scoped (3) | `PayrollRunEntry`, `PayslipEmailJob`, `LeaveAllowanceEmailJob` | `payroll_run.company` |
| Appraisal children (4) | `AppraisalAssignment`, `Metric`, `Review`, `Rating` | `appraisal.company` |
| Chat (3) | `CompanyChatMessage`, `CompanyChatReadState`, `CompanyChatRoomMember` | `room.company` |
| Company-setting child (1) | `CompanyHealthInsuranceTier` | `company_payroll_setting.company` |
| Hiring (1) | `CandidateConsent` | `candidate.company` |
| Survey (1) | `SurveyQuestion` | `survey_template.company` |
| Offboarding (1) | `OffboardingTask` | `checklist.company` |
| System log (1) | `AuditTrail` | content-object's company (or user's); see A2 |

### Deliberately NOT tenant-scoped (no FK)

`StatutoryRateVersion` (national rates, shared), `NotificationTemplate`
(global template library), `NotificationTypePreference` (global preference
defaults).

## 5. Removal order

1. **Fix A1 + A2** (audit-trail leaks) — A2 first needs `AuditTrail.company`
   (nullable FK + backfill + `save()` default from content object).
2. Add nullable `company` FK + backfill to the **11 accounting tables**
   (migration per table; update `unique_together` to include company where
   the natural key is per-company, e.g. `TransactionNumber(fiscal_year, prefix)`).
3. Re-verify accounting views' existing explicit scoping still holds, then
   **remove the lockdown** (set `ACCOUNTING_SUPERUSER_ONLY_UNTIL_TENANT_SCOPED=False`
   in prod) — finance/non-superusers then reach accounting pages safely.
4. Adopt `CompanyOwnedModel` on the accounting tables + the payroll table
   list above (matrix Pillar 5 rows), then flip
   `TENANT_SCOPING_ENFORCED=True` + `ALLOW_DEFAULT_COMPANY_FALLBACK=False`.

## 6. Notes

- `AuditTrail` (payroll) also carries the known cascade-delete crash
  (`payroll/audit_signal.py::log_employee_delete`) — same table, fix both
  together.
- The two audit-trail lists (accounting A1, payroll A2) are the only
  confirmed live cross-tenant reads in the scanned surface; everything else
  is scoped or parent-scoped, with the form-default pattern (B1) the main
  silent-risk to guard with a test.
