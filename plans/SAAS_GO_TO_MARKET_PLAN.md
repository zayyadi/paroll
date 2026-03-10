# SaaS Go-To-Market Plan (Website + Onboarding + Support)

Date: 2026-02-28
Status: Proposed
Owner: Product/Engineering
Scope: Public SaaS business surface for payroll platform (landing, setup/order, support, about/trust)

## 1) Objectives

- Launch a conversion-focused public website that clearly sells the payroll product.
- Enable self-serve company onboarding from signup to first successful payroll run.
- Stand up reliable customer care operations (knowledge base, ticketing, SLA, status updates).
- Build trust/compliance posture visibility (security, privacy, legal, reliability pages).

## 2) North-Star + KPI Targets (first 90 days)

- North-star: `Time to First Successful Payroll Run (TTFPR)`.
- Landing -> signup conversion: target >= 4% (optimize toward 6%+).
- Signup -> company setup completed: target >= 55%.
- Setup completed -> first payroll run: target >= 40%.
- Trial -> paid conversion: target >= 20% (or set based on pricing model).
- First response time (support): < 1 business hour.
- P95 resolution time (support): < 24 business hours.
- Core Web Vitals pass rate: >= 75% sessions by URL group.

## 3) Workstreams

### A) Public Website

Required pages:
- `/` Landing page (hero, value proposition, proof, CTA, FAQ).
- `/pricing` Transparent plans, monthly/annual toggle, add-ons.
- `/about` Company narrative, team, principles, hiring/contact hooks.
- `/support` Support channels, SLA, knowledge base entry point.
- `/security` Security + data handling + compliance trust page.
- `/contact` Sales + support inquiry form.
- `/legal/privacy`, `/legal/terms`, `/legal/cookies`.

Must-have UX:
- Primary CTA: `Start free trial`.
- Secondary CTA: `Book demo`.
- Social proof and implementation timeline block.
- Fast mobile performance and clear navigation hierarchy.

### B) Setup + Ordering Funnel

Onboarding flow steps:
1. Create account and verify email.
2. Create/select company workspace.
3. Company profile + jurisdiction/tax setup.
4. Employee import (CSV/template + validation).
5. Payroll settings (frequency, allowances, deductions, pension/tax rules).
6. Approval and role setup.
7. Test payroll run (dry run) + errors checklist.
8. Payment method + subscription checkout.
9. Go-live checklist and first payroll confirmation.

Must-have controls:
- Save-and-resume onboarding.
- Progress state and completion score.
- Inline validation + remediation guidance.
- Admin invite during setup.

### C) Customer Care Operations

Support stack baseline:
- Ticket intake (web form + in-app + email).
- Knowledge base (setup, imports, payroll errors, statutory remittance, troubleshooting).
- Auto-triage categories: billing, technical, compliance, onboarding, account access.
- SLA policy + escalation matrix.
- Service status page and incident communication template.

Minimum operating model:
- L1 first response and triage.
- L2 product/engineering escalation path.
- Weekly support review (top issues, deflection, backlog fixes).

### D) Trust, Compliance, and Risk

- Publish security controls summary (auth, data isolation, backups, access controls).
- Publish privacy and retention policy.
- Publish uptime/incident disclosure process.
- Provide clear cancellation + billing policy in product and website.
- Add audit logs for onboarding, billing, and support actions.

## 4) Repository Implementation Map

Current state observations:
- Public root currently routes into app URLs directly.
- Existing SaaS tenant foundations are present in `company/`, `users/`, and `core/settings_saas.py`.
- Prior packaging plan exists in `plans/SAAS_PACKAGING_PLAN.txt`.

Planned additions:
- `marketing/` Django app for public pages and lead capture.
- `templates/marketing/*` for landing/pricing/about/support/security/contact/legal.
- `marketing/urls.py` and route split in `core/urls.py`.
- `onboarding/` app (or module) for setup wizard state machine.
- `support/` app for tickets, KB, SLAs, and status notices.
- `billing/` integration module for subscriptions and cancellation workflow.
- Analytics events in existing app/service layer.

## 5) 12-Week Delivery Plan

### Phase 1 (Weeks 1-2): Strategy + Instrumentation
- Finalize ICP and messaging architecture.
- Define funnel events and analytics schema.
- Define pricing hypotheses and packaging experiment matrix.
- Deliverables:
  - Messaging doc
  - Funnel event spec
  - KPI dashboard spec

### Phase 2 (Weeks 3-5): Public Website MVP
- Build landing/pricing/about/contact/security/support/legal pages.
- Add lead form routing and CRM/email integration.
- Add SEO metadata, structured data, and baseline performance budgets.
- Deliverables:
  - Marketing app v1 in production
  - Baseline conversion tracking

### Phase 3 (Weeks 5-8): Setup + Checkout Funnel
- Implement onboarding wizard and persistent setup state.
- Add import validator and dry-run payroll checks.
- Integrate subscription checkout and cancellation controls.
- Deliverables:
  - End-to-end self-serve onboarding v1
  - Trial-to-paid flow live

### Phase 4 (Weeks 6-9): Customer Care
- Launch support center + ticketing + KB.
- Publish SLA and escalation runbooks.
- Launch status communication workflow.
- Deliverables:
  - Support operations v1
  - Incident communication templates

### Phase 5 (Weeks 9-12): Optimization
- A/B testing: hero messaging, CTA placement, pricing table configuration, onboarding step friction.
- Improve drop-off points based on analytics.
- Add lifecycle email nudges for incomplete onboarding.
- Deliverables:
  - CRO report
  - Updated backlog for quarter 2

## 6) Immediate Backlog (next 10 engineering tasks)

1. Create `marketing` app and wire `core/urls.py` route split.
2. Implement public page templates and navigation shell.
3. Add lead/contact form model + admin queue.
4. Add analytics event helper and event taxonomy constants.
5. Create onboarding state model (`company`, `step`, `status`, `payload`, `updated_at`).
6. Implement onboarding wizard endpoints + save/resume.
7. Add CSV employee import validator with downloadable error report.
8. Implement support ticket models and staff/admin views.
9. Add `security`, `privacy`, `terms` content pages.
10. Add smoke tests for public routes, onboarding progression, and support ticket creation.

## 7) Risks + Mitigations

- Risk: Scope expansion delays launch.
  - Mitigation: Strict MVP cut line per phase and weekly scope review.
- Risk: Poor onboarding completion.
  - Mitigation: Save/resume, inline remediation, guided checklist, lifecycle nudges.
- Risk: Support load spikes post-launch.
  - Mitigation: KB-first workflow, triage tagging, escalation policy.
- Risk: Compliance/trust gaps hurt conversion.
  - Mitigation: Publish trust pages early and align with legal review.

## 8) Definition of Done

- Public pages live with clear value proposition and measurable CTA events.
- New company can complete onboarding and run first payroll without manual engineering intervention.
- Support team can receive, triage, and resolve tickets with SLA tracking.
- Legal/trust pages are accessible from global navigation/footer.
- KPI dashboard shows full funnel from visit -> paid account.

## 9) Track Structure Proposal

- Track 1: Marketing website foundation.
- Track 2: Onboarding/setup wizard.
- Track 3: Billing and subscription lifecycle.
- Track 4: Support center and operations.
- Track 5: CRO and analytics optimization.

Each track should have:
- `spec.md` (problem, users, constraints, acceptance criteria)
- `plan.md` (implementation tasks, owners, dependencies, checkpoints)

