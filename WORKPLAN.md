# Recommendations Implementation Workplan

**Start Date:** May 30, 2026  
**Total Effort:** ~8-10 weeks (full scope)  
**Team Size:** 2-3 developers  

---

## Phase 1: Critical Security & Testing (Weeks 1-2)
**Effort:** 1 sprint | **Risk:** High | **Impact:** Critical

### Tasks
1. **Remove Dead Code** (3 days)
   - Search for all commented code blocks in `payroll/models/`, `payroll/views/`
   - Remove unused imports and commented functions
   - PR: `refactor/remove-dead-code`

2. **Implement Row-Level Security** (5 days)
   - Create `core/rla_mixin.py` for row-level access control
   - Add department filtering to employee views
   - Add reporting-line restrictions
   - PR: `security/row-level-access-control`

3. **Add Leave Workflow Integration Tests** (5 days)
   - Create `tests/integration/test_leave_complete_workflow.py`
   - Test: apply → manager approve → HR approve → balance deduct → payroll recalc
   - Target: 3 E2E tests
   - PR: `test/leave-workflow-integration`

### Definition of Done
- All commented code removed
- Row filtering applied to EmployeeProfile queries
- 3 integration tests passing

---

## Phase 2: Architecture Refactoring (Weeks 3-4)
**Effort:** 2 sprints | **Risk:** Medium | **Impact:** High

### Tasks
1. **Split View Modules** (8 days)
   - `payroll/views/employee_view.py` → split into 7 files:
     - `employees.py` (CRUD)
     - `attendance.py` (clock in/out, records)
     - `documents.py` (doc management)
     - `assets.py` (asset tracking)
     - `performance.py` (appraisals, reviews)
     - `surveys.py` (survey workflows)
     - `learning.py` (learning management)
   - Update `urls.py` imports
   - PR: `refactor/split-employee-views`

2. **Modularize Forms** (5 days)
   - Create `payroll/forms/` subdirectory structure:
     - `__init__.py`
     - `employee_forms.py`
     - `hiring_forms.py`
     - `leave_forms.py`
     - `payroll_forms.py`
     - `attendance_forms.py`
   - Update imports in views
   - PR: `refactor/modularize-forms`

3. **Move Disciplinary System** (5 days)
   - Create `payroll/discipline/` app
   - Move `DisciplinarySanction` from `accounting/models.py`
   - Create discipline views, forms, urls
   - Add migrations
   - PR: `refactor/move-discipline-to-hr`

### Definition of Done
- All view imports update and tests passing
- Forms can be imported from new locations
- Discipline module fully functional
- No test failures

---

## Phase 3: Service Layer Enhancement (Weeks 5-6)
**Effort:** 2 sprints | **Risk:** Low | **Impact:** High

### Tasks
1. **Extract Signal Logic to Services** (5 days)
   - Audit `payroll/signals.py`
   - Move business logic into `payroll/services/`
   - Keep signals as thin dispatchers
   - PR: `refactor/extract-signal-logic`

2. **Add Type Hints** (8 days)
   - Priority 1: All services (2 days)
   - Priority 2: All views (4 days)
   - Priority 3: All forms (2 days)
   - Configure mypy in CI/CD
   - PR: `quality/add-type-hints`

3. **Create Service Documentation** (2 days)
   - Document each service's responsibility
   - Create `/docs/services.md` with catalog
   - PR: `docs/service-catalog`

### Definition of Done
- 100% of services have type hints
- mypy passes with no errors
- All tests passing

---

## Phase 4: Feature Completion (Weeks 7-8)
**Effort:** 2 sprints | **Risk:** Medium | **Impact:** Medium

### Tasks
1. **Leave System Enhancements** (8 days)
   - Add leave carryover model
   - Implement leave calendar view
   - Add blackout date configuration
   - Add Labour Act compliance checks
   - PR: `feature/leave-system-enhancements`

2. **Data Retention Policies** (5 days)
   - Create retention policy configuration
   - Add Celery tasks for:
     - Candidate archival (1 year)
     - Survey archival (2 years)
     - Disciplinary archival (3 years)
   - PR: `feature/data-retention-policies`

3. **Consent Enhancement** (4 days)
   - Create `CandidateConsent` model
   - Add consent tracking and audit trail
   - Implement re-consent workflow
   - PR: `feature/enhanced-consent-tracking`

### Definition of Done
- Leave carryover calculations working
- Retention tasks scheduled and tested
- Consent model with audit trail

---

## Phase 5: Testing & Quality (Weeks 9-10)
**Effort:** 2 sprints | **Risk:** Low | **Impact:** Critical

### Tasks
1. **Employee CRUD Tests** (4 days)
   - Create `tests/features/test_employee_crud.py`
   - Cover: create, read, update, delete, search
   - Target: 85%+ coverage
   - PR: `test/employee-crud-coverage`

2. **Hiring Pipeline Tests** (4 days)
   - Create `tests/features/test_hiring_pipeline.py`
   - Cover: requisition → candidates → offers → acceptance
   - PR: `test/hiring-pipeline-coverage`

3. **Attendance & Performance Tests** (4 days)
   - Create `tests/features/test_attendance.py`
   - Create `tests/features/test_performance_reviews.py`
   - PR: `test/attendance-performance-coverage`

4. **Query Optimization Review** (3 days)
   - Profile high-traffic views with django-debug-toolbar
   - Add select_related/prefetch_related where needed
   - Document query optimization patterns
   - PR: `perf/query-optimization`

### Definition of Done
- 80%+ code coverage for HR features
- No N+1 query problems
- All integration tests passing

---

## Quick Wins (Can Start Immediately)
**Low effort, high value:**

1. **Remove Chat Module** (1 day)
   - Archive `payroll/consumers/` 
   - Remove WebSocket routes
   - Document external chat integration plan
   - PR: `cleanup/archive-chat-module`

2. **Add Salary History Model** (2 days)
   - Create `SalaryHistory` model
   - Add migration
   - Add service to track changes
   - PR: `feature/salary-history-tracking`

3. **Standardize Permissions** (3 days)
   - Document permission matrix
   - Add @permission_required to all views
   - Create permission factory for tests
   - PR: `security/standardize-permissions`

---

## Timeline View
```
Week 1-2:   ████ Remove dead code, Row security, Leave tests
Week 3-4:   ████████ Split views, Forms, Discipline module  
Week 5-6:   ████ Signals→Services, Type hints, Docs
Week 7-8:   ████ Leave enhancements, Retention, Consent
Week 9-10:  ████ CRUD tests, Hiring tests, Performance optimization
```

---

## Team Allocation (2-3 Developers)

**Developer 1 (Senior):**
- Phase 2: View/Form refactoring
- Phase 3: Service layer & type hints
- Code review all PRs

**Developer 2 (Mid-Level):**
- Phase 1: Dead code removal, RLA implementation
- Phase 4: Feature enhancements
- Integration test creation

**Developer 3 (Optional/Junior):**
- Phase 5: Unit test coverage
- Documentation updates
- Query profiling

---

## Success Metrics

| Metric | Current | Target | Timeline |
|--------|---------|--------|----------|
| Dead code blocks | 30+ | 0 | Week 2 |
| Row-level security coverage | 0% | 100% | Week 2 |
| Integration tests | 5 | 15+ | Week 10 |
| Type hint coverage | 5% | 80% | Week 6 |
| Test coverage (HR features) | 5% | 80% | Week 10 |
| Query problems (N+1) | Unknown | 0 | Week 10 |
| Code duplication | High | Low | Week 4 |

---

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| Large refactors break tests | Feature branch testing, revert plan |
| View splitting increases complexity | Pair programming, comprehensive tests |
| Migration issues | Test on staging, rollback procedure |
| Team knowledge gaps | Documentation, pair programming |

---

## Dependencies & Prerequisites

- [ ] Staging environment for testing
- [ ] Django 4.2+ (for type hint compatibility)
- [ ] mypy configured in project
- [ ] CI/CD pipeline to validate PRs
- [ ] Code review process established

---

## Acceptance Criteria (Phase Completion)

**Phase 1:** ✅ All dead code removed, row security functional, 3+ integration tests  
**Phase 2:** ✅ View/form structure modularized, all imports working, zero regressions  
**Phase 3:** ✅ Type hints on all services/views, mypy passing  
**Phase 4:** ✅ Leave carryover working, retention tasks scheduled, consent enhanced  
**Phase 5:** ✅ 80%+ test coverage, no N+1 queries, performance baseline established

---

## Post-Implementation Tasks (Future)

- [ ] Chat module replacement with Slack/Teams integration
- [ ] Standup module migration to separate app
- [ ] Organizational chart feature
- [ ] Exit interview workflow
- [ ] Compensation band system
- [ ] Document expiry tracking

---

**Prepared:** May 30, 2026  
**Next Review:** June 6, 2026 (end of Phase 1)
