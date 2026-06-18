---
name: project-deep-dive
description: >-
  Systematic codebase analysis for ERP/Django projects. Launches parallel
  explore subagents to map architecture, business logic, frontend, security,
  and gaps — then synthesizes findings into a comprehensive audit report.
  Use when asked to "deep dive", "audit", "analyze", "review codebase",
  "assess implementation", or "suggest improvements".
---

# Project Deep Dive

Systematic codebase analysis using parallel subagent exploration. Designed for complex ERP/Django projects where understanding the full picture requires examining multiple domains simultaneously.

## When to Use

- User asks for a "deep dive", "audit", or "codebase analysis"
- Starting work on an unfamiliar project
- Planning feature additions or refactoring
- Security or architecture review
- Onboarding new team members

## Workflow

### Phase 1: Parallel Exploration (3 subagents)

Launch 3 explore subagents simultaneously, each focused on a domain:

**Subagent 1 — Structure & Architecture**
- Project structure: all directories, key files, package.json/requirements.txt
- Framework identification (Django, FastAPI, etc.)
- Database models: ALL models and their fields
- URL routing: all API endpoints
- Configuration: settings, docker, CI/CD
- Authentication and session management

**Subagent 2 — Business Logic & ERP Features**
- All views/API logic and business processes implemented
- Employee management (onboarding, offboarding, transfers, promotions)
- Payroll calculation logic (taxes, deductions, overtime, bonuses, benefits)
- Leave/time-off management
- Reporting and analytics capabilities
- Integration points (email, payment gateways, government systems)

**Subagent 3 — Frontend, Security & Gaps**
- Frontend/templates (HTML, React, Vue, template files)
- Serializers and data validation
- Permissions and authorization (DRF permissions, decorators)
- Custom middleware
- Error handling patterns
- Logging and audit trails
- Search/filtering capabilities
- Testing coverage and quality

### Phase 2: Synthesis (1 subagent)

After exploration completes, launch a synthesis subagent with the collected findings. Prompt template:

```
Based on the following exploration of a [framework] [project-type] called '[name]', create a comprehensive audit analysis.

## Exploration Results
[Insert findings from all 3 explore subagents]

## Required Output
1. Executive Summary — maturity level (1-10), production readiness, key risks
2. Architecture Assessment — strengths, weaknesses, technical debt
3. Feature Completeness — what's implemented vs. what's missing for [domain]
4. Security Review — vulnerabilities, access control gaps, data protection
5. Recommendations — prioritized list (HIGH/MEDIUM/LOW) with effort estimates
6. Next Steps — concrete action items for the next sprint/phase

Format as a professional audit report with tables, scores, and clear status indicators (✅/⚠️/❌).
```

### Phase 3: Report Delivery

Save the synthesized report as `[MODULE]_AUDIT_REPORT.md` in the project root. Include:
- Executive summary with maturity score
- Section-by-section findings with status indicators
- Prioritized recommendations table
- Next steps with effort estimates

## Tips

- Adjust subagent prompts based on project type (ERP, SaaS, e-commerce, etc.)
- For smaller projects, 2 subagents may suffice (structure + features, frontend + security)
- Include specific domain questions (e.g., "Nigeria tax compliance" for Nigerian payroll)
- Reference existing audit reports in the project for consistency in format
