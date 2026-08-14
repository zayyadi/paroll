# Tenant Isolation — Acceptance Matrix

Gate for flipping `ALLOW_DEFAULT_COMPANY_FALLBACK` off (the multi-tenant
retrofit's final step). Every criterion is backed by a runnable test in
`tests/test_tenant_isolation.py`. Run the gate with:

```bash
python manage.py test tests.test_tenant_isolation
```

Status legend: ✅ gate green · ⚠️ tracked risk (documented, not yet encoded).
No `@expectedFailure` blockers remain; the suite must show 0 unexpected
successes.

## Pillar 1 — Natural-key isolation

| # | Criterion | Test | Status |
|---|---|---|---|
| 1.1 | The same payroll-run name + slug + pay period can exist in two companies, each resolving its own row | `test_same_payroll_run_name_and_slug_coexist_in_two_companies` | ✅ |
| 1.2 | A duplicate natural key inside ONE company is still rejected (per-company uniqueness holds) | `test_duplicate_payroll_run_name_within_one_company_is_rejected` | ✅ |
| 1.3 | Slug-routed URLs resolve to the caller's own run even when slugs are identical across companies | `test_pay_period_detail_resolves_only_the_callers_company_run` | ✅ |
| 1.4 | Two companies can use the same employee number (e.g. both "A-001") | `test_same_employee_number_reusable_across_companies` | ✅ company-scoped constraint `uniq_employee_company_emp_id` (migration `0065`) |
| 1.5 | A duplicate natural key inside ONE company is still rejected (employee number) | `test_duplicate_employee_number_within_one_company_is_rejected` | ✅ |
| 1.6 | Tax IDs (NIN/TIN) are unique per company, reusable across tenants | `test_same_tax_ids_reusable_across_companies` / `test_duplicate_tax_ids_within_one_company_is_rejected` | ✅ `uniq_employee_company_nin` / `uniq_employee_company_tin_no` key on deterministic SHA-256 digests — Fernet is non-deterministic, so the old global `unique=True` on the ciphertext columns was a dead constraint and could never fire; the digests (backfilled in migration `0065`) make it enforceable |
| 1.7 | Journal transaction numbers restart per company and stay unique inside one | `test_same_journal_transaction_number_reusable_across_companies` / `test_duplicate_journal_transaction_number_within_one_company_is_rejected` | ✅ `uniq_journal_company_transaction_number` (migration `0018`) |
| 1.8 | Disciplinary case numbers restart per company (no global-latest lookup) and stay unique inside one | `test_same_case_number_reusable_across_companies` / `test_duplicate_case_number_within_one_company_is_rejected` | ✅ `uniq_case_company_case_number` (migration `0018`); generator lookup is company-scoped |

## Pillar 2 — Zero cross-tenant rows

| # | Criterion | Test | Status |
|---|---|---|---|
| 2.1 | Company-scoped querysets return exactly the owning company's rows (Payroll, PayrollRun, PayrollEntry, RunEntry, RemittanceRecord, BankPaymentFile) | `test_company_scoped_querysets_never_return_other_companies_rows` | ✅ |
| 2.2 | Report aggregates (e.g. PAYE report totals) exclude the other company's payroll even for identical run names | `test_report_totals_are_company_scoped` | ✅ |
| 2.3 | The compliance calendar shows only the company's own obligations, with its own amounts | `test_compliance_calendar_only_includes_own_company_obligations` | ✅ |
| 2.4 | The same obligation + pay period is legal in two companies and stays isolated | `test_remittance_records_allow_same_period_in_both_companies` | ✅ |

## Pillar 3 — Tenant-safe caching

| # | Criterion | Test | Status |
|---|---|---|---|
| 3.1 | Cache keys keyed by stable identifiers isolate two companies' employees | `test_unread_count_cache_keys_are_stable_per_employee_id` | ✅ (the fix contract) |
| 3.2 | Same-named employees in different companies must never share a cache entry | `test_unread_count_cache_does_not_collide_across_companies` | ✅ `NotificationCacheService._get_cache_key` delegates to `tenant_cache_key` — EmployeeProfile parts normalize to pk and carry their company, so keys are `tenant:<company pk>:notifications:<pk>:<suffix>` |
| 3.3 | National data (statutory rate versions) is shared by design — not per-company, not a leak | `test_statutory_rates_are_national_not_tenant_scoped` | ✅ |
| 3.4 | Every tenant-data cache key carries the company dimension (OWASP multi-tenant caching rule) | `test_model_part_uses_pk_and_company` / `test_same_named_employees_in_different_companies_get_distinct_keys` / `test_context_supplies_company_for_string_parts` | ✅ `tenant_cache_key(...)` in `company/tenancy.py`: model parts → pk + their company; string parts → current context company; unprefixed only when no company is derivable (stable ids still prevent collisions) |
| 3.5 | Cache invalidation matches the tenant-scoped write keys | `test_mark_all_read_clears_cached_badge_count` (payroll/tests_notification_mark_read.py) | ✅ `Notification._invalidate_cache` builds keys through `tenant_cache_key` with the recipient object |
| 3.6 | Auth-level keys (login lockout, OTP, MFA step-up) and national reference caches are intentionally NOT tenant-prefixed | — | ⚠️ Documented at the sites (`accounting/mfa.py`, `users/views.py`, `payroll/utils.py` statutory versions): account-scoped security controls and shared national data must stay global |

## Pillar 4 — Background-task scoping

| # | Criterion | Test | Status |
|---|---|---|---|
| 4.1 | The payslip-email task processes only the run it was created for: sends only that company's employees, leaves the other company's job queued | `test_payslip_email_task_only_sends_for_its_own_company_run` | ✅ |
| 4.2 | Background jobs resolve to the company of the run they reference | `test_payslip_email_job_belongs_to_its_run_company` | ✅ |

## Pillar 5 — Fail-closed read scoping (contextvars layer)

| # | Criterion | Test | Status |
|---|---|---|---|
| 5.1 | A company context primitive exists that sets/restores per block, including nesting | `test_company_context_sets_and_restores` / `test_nested_company_contexts_stack` | ✅ `company_context(...)` in `company/tenancy.py` |
| 5.2 | `get_user_company` establishes the contextvars context when it resolves a company | `test_get_user_company_establishes_context` / `test_get_user_company_switches_context` | ✅ |
| 5.3 | With `TENANT_SCOPING_ENFORCED=True`, querying a `CompanyOwnedModel` with no context raises `CompanyContextRequired` (fail-closed) | `test_no_context_raises_for_adopted_models` | ✅ |
| 5.4 | With context set, reads are scoped to that company; another company's rows are unreachable even via an explicit filter | `test_queries_scope_to_current_company` / `test_explicit_other_company_filter_under_context_is_empty` | ✅ |
| 5.5 | `all_objects` remains an unscoped escape hatch (migrations, backfills, cross-tenant admin) | `test_all_objects_escape_hatch_is_unscoped` | ✅ |
| 5.6 | `TENANT_SCOPING_ENFORCED=False` preserves legacy unscoped reads when no context is set | `test_no_context_returns_unscoped_queryset` | ✅ |
| 5.7 | The request lifecycle sets context for the view and clears it afterwards (no cross-request/thread leak) | `test_request_sets_context_for_view_and_clears_after` / `test_context_does_not_leak_between_users_requests` | ✅ middleware + `get_user_company` wiring |
| 5.8 | Adopted models are the only ones scoped today; adoption is incremental | — | ⚠️ adopted: `RemittanceRecord`, `PublicHoliday`. Every `CompanyOwnedModel` subclass inherits the guard automatically — widening = changing each model's base + adding tests |

## Known risks outside the four pillars (pre-flip checklist)

- ⚠️ `payroll/audit_signal.py::log_employee_delete` crashes when an
  EmployeeProfile is deleted after its user is already gone (cascade order).
  Not isolation itself, but it surfaced during gate verification and will bite
  tenant teardown flows.
- ⚠️ Super-admin dashboards mix global and company-scoped aggregates (flagged
  in the multi-tenant research) — verify before flip.
- ✅ Fallback off already rejects missing companies at the model boundary
  (`accounting/models.py`, `users/manager.py`, `employee_profile.py`) — covered
  by `tests/test_payroll_security_hardening.py`.

## Flip procedure

1. `python manage.py test tests.test_tenant_isolation tests.test_tenant_scoping` —
   must show 0 failures/errors and 0 unexpected successes. All blockers
   (1.4, 3.2) landed; no `@expectedFailure` markers remain.
2. Widen `CompanyOwnedModel` adoption (each remaining tenant model + matrix
   rows), then flip `TENANT_SCOPING_ENFORCED=True` and
   `ALLOW_DEFAULT_COMPANY_FALLBACK=False` in `core/settings_test.py` and run
   the full suite — any unscoped/unsupported query now fails loudly instead of
   leaking.
3. Delete the `accounting` superuser-only lockdown once the suite is green.
