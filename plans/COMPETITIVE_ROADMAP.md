# PayNest Competitive Roadmap

Prioritized feature-gap roadmap against the Nigeria payroll/HR competitive set, sized by
engineering effort and competitive impact. Every item carries a **Status** so the plan doubles
as a living ship tracker — see the [Status section](#status-tracking) at the end.

- Date: 2026-08-14
- Owner: Product / Engineering
- Competitive set: **HRPayHub**, **SeamlessHR**, **Workpay**, **HumanManager** (global benchmark: Endeavour)

## Competitive baseline (what drives the gaps)

| Vendor | Position | Where PayNest lags / wins |
| --- | --- | --- |
| **HRPayHub** | SME payroll, published ₦ pricing (₦499 / ₦999 per user tiers) | Lags on *published pricing* and *payment/disbursement rails*; wins on statutory depth |
| **SeamlessHR** | Mid-market enterprise HR suite (recruiting, performance, HRIS + payroll) | Lags on *HR module breadth*; wins on payroll compliance depth |
| **Workpay** | SME payroll + **EWA** + strong **mobile app** + remittance | Lags on *EWA*, *mobile*, and *disbursement*; wins on statutory correctness |
| **HumanManager** | Affordable SME HR + payroll | Lags on *pricing transparency* and *self-serve onboarding* |
| **Endeavour** (global) | Per-user SaaS, **$30 + $1/user** model | Benchmark for *per-user pricing mechanics*, not a local competitor |

**PayNest's wedge**: "from calculation to remittance" statutory completeness, reform-readiness,
and governance controls. The roadmap closes the gaps that undercut that wedge — visible pricing,
actual remittance rails, and the modern payment/mobile surfaces competitors lead with.

## Effort & impact legend

- **Effort**: S ≤ 1 sprint · M 1–2 sprints · L ≈ 1 quarter · XL 2+ quarters
- **Competitive impact**: High (differentiator or parity with a named competitor) ·
  Medium (visible improvement) · Low (hygiene/positioning)
- **Priority**: P1 = ship first (high impact, low-to-moderate effort) · P2 = next ·
  P3 = when capacity allows

## Prioritized roadmap

| # | Item | Gap closed vs | Effort | Competitive impact | Priority | Status |
| --- | --- | --- | --- | --- | --- | --- |
| R1 | **Published ₦ pricing tiers** (module gating + free tier) | HRPayHub (₦499/₦999), HumanManager, Endeavour ($30+$1) | M | High | P1 | In progress |
| R2 | **Remita disbursement** (payroll → salary payment rails) | HRPayHub, Workpay | L | High | P1 | Not started |
| R3 | **Earned Wage Access (EWA)** | Workpay | L | High | P2 | In progress |
| R4 | **Mobile app** (phased: PWA → wrappers) | Workpay | XL | Medium | P2 | Not started |
| R5 | **Annual statutory e-filing** (NTAA/PIT return submission) | All (compliance wedge) | M | Medium | P3 | Not started |
| R6 | **In-app competitor tracking** (pricing/features/status per vendor) | Positioning hygiene | S | Low | P3 | Not started |

## Item details

### R1 — Published ₦ pricing tiers (P1)
- **Why**: HRPayHub publishes ₦499/₦999 per-user tiers; PayNest's marketing promises statutory
  completeness but shows no prices. Buyers benchmark on price first in the SME segment.
- **Scope**: `/pricing` page (monthly/annual toggle, per-user ₦ tiers benchmarked against
  HRPayHub and Endeavour's $30+$1 mechanics), module gating (payroll core vs HR add-ons),
  free-tier proposal (e.g. small headcount, no disbursement) wired into the SaaS packaging.
- **Dependencies**: SaaS packaging settings overlay (`core.settings_saas`), tenant limits.

### R2 — Remita disbursement (P1)
- **Why**: completes the "from calculation to remittance" promise — the single strongest
  missing capability versus HRPayHub/Workpay. Without it, PayNest computes but does not pay.
- **Scope**: Remita API integration (mandate collection, salary payment mandate), company bank
  account capture, batch disbursement from a payroll run, disbursement status polling +
  reconciliation, and full audit trail of outbound payments.
- **Dependencies**: existing payroll-run model, `RemittanceRecord` tracker, audit-trail service.
- **Risk**: third-party API stability + bank settlement; start with a sandboxed pilot company.

### R3 — Earned Wage Access (P2)
- **Why**: Workpay's flagship differentiator; strong retention driver for employees and a
  visible reason to switch payroll providers.
- **Scope**: EWA advance engine (earned-but-unpaid cap, frequency limits), funding via a
  partner/own float, repayment reconciliation against the next run, employer-level controls
  and risk limits.
- **Dependencies**: R2 (disbursement rails), payroll-run computation.

### R4 — Mobile app (P2)
- **Why**: Workpay's mobile-first experience is a named lead; employee self-service on phone is
  expected in the SME segment.
- **Scope**: phase 1 = responsive PWA (payslips, leave, notifications, EWA); phase 2 = native
  wrappers (capacitor/RN) with biometric login.
- **Dependencies**: none hard; reuse existing employee-dashboard views.

### R5 — Annual statutory e-filing (P3)
- **Why**: the compliance wedge is PayNest's moat; automated PAYE annual return submission
  (due 31 Jan) extends "remittance" to "filing" and differentiates against all four.
- **Scope**: annual emoluments return export in IRS-ready format, submission status tracking
  in the compliance calendar, per-state IRS variations.

### R6 — In-app competitor tracking (P3)
- **Why**: keeps the positioning current without re-researching the market each quarter;
  low-effort hygiene that guards the roadmap itself.
- **Scope**: a small competitor model (name, pricing, features, status) + an admin page; the
  research this roadmap is based on becomes a quarterly data-entry task instead of a project.

## Status tracking

**Legend**: Not started · In progress · Blocked · Shipped

Every item above starts as **Not started** and is flipped as it ships. Append one line to the
ship log below when an item lands (date, item, what shipped, validation), and update the
table's Status column to `Shipped`.

### Ship log

- **2026-08-14 · R1 (in progress)**: published ₦ tiers shipped on the marketing pricing page — `PricingPlan` model + admin, seed migration (Free ₦0 / Starter ₦499 / Growth ₦999 / Enterprise custom, annual at −10%), monthly-vs-annual toggle. Module-gating *enforcement* in SaaS packaging still pending; free-tier headcount cap is display-only for now.
- **2026-08-14 · R3 (in progress)**: EWA engine shipped — `payroll/services/ewa.py` (earned-but-unpaid advance cap, per-cycle frequency rules, net-pay take-home guardrail), company EWA policy on `CompanyPayrollSetting` (editable in settings), `is_ewa` flag on IOU, self-service `/request-ewa/` page with eligibility panel, repayment via the existing salary-deduction flow (1-month tenor). Funding partner/disbursement rails and EWA repayment reconciliation against actual runs still pending (depends on R2).
