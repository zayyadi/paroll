from datetime import date
from decimal import Decimal

from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, TestCase

from payroll.models import EmployeeTransfer, Promotion, OffboardingChecklist, HiringCandidate, JobOffer
from tests.features.test_hiring_pipeline import HiringPipelineFeatureTests
from tests.approval_helpers import approval_user
from payroll.services.hiring import create_job_offer, release_job_offer, accept_job_offer


class HiringAdminIntegrityTests(TestCase):
    setUp = HiringPipelineFeatureTests.setUp
    _candidate = HiringPipelineFeatureTests._candidate
    _grant = HiringPipelineFeatureTests._grant
    def _offer(self):
        return create_job_offer(candidate=self._candidate(), title="Engineer", employment_type="full_time",
            salary_amount=Decimal("250000"), currency="NGN", start_date=date(2026, 7, 1), created_by=self.user)

    def test_cannot_fabricate_accepted_offer_through_creation(self):
        offer = self._offer()
        offer.pk = None
        offer.status = "accepted"
        with self.assertRaises(PermissionDenied):
            offer.save()

    def test_cannot_skip_release_or_rewind_released_offer(self):
        offer = self._offer()
        with self.assertRaises(PermissionDenied):
            JobOffer._base_manager.filter(pk=offer.pk).update(status="accepted")
        release_job_offer(offer=offer, actor=self.checker)
        offer.refresh_from_db()
        with self.assertRaises(PermissionDenied):
            JobOffer._base_manager.filter(pk=offer.pk).update(status="draft")
        with self.assertRaises(PermissionDenied):
            JobOffer._base_manager.filter(pk=offer.pk).update(created_by=self.checker)

    def test_real_release_allows_acknowledgment_but_freezes_terminal_history(self):
        offer = self._offer()
        release_job_offer(offer=offer, actor=self.checker)
        offer.refresh_from_db()
        accept_job_offer(offer, accepted_by=self.user)
        offer.refresh_from_db()
        self.assertEqual(offer.status, "accepted")
        with self.assertRaises(PermissionDenied):
            JobOffer._base_manager.filter(pk=offer.pk).update(accepted_at=None)

    def test_hr_admin_scopes_querysets_and_foreign_keys(self):
        from company.models import Company
        foreign = Company.objects.create(name="Other hiring company")
        candidate = self._candidate()
        from payroll.models import Position, JobRequisition
        foreign_position = Position.objects.create(company=foreign, title="Engineer")
        foreign_requisition = JobRequisition.objects.create(company=foreign, position=foreign_position, title="Engineer")
        foreign_candidate = HiringCandidate.objects.create(company=foreign, requisition=foreign_requisition,
            first_name="Foreign", last_name="Candidate", email="foreign@example.test")
        foreign_user = approval_user(foreign)
        foreign_employee = foreign_user.employee_user
        foreign_employee.company = foreign
        foreign_employee.save(update_fields=["company"])
        foreign_records = {
            HiringCandidate: foreign_candidate,
            JobOffer: JobOffer.objects.create(company=foreign, candidate=foreign_candidate, title="Engineer",
                employment_type="full_time", salary_amount=Decimal("250000"), start_date=date(2026,7,1)),
            EmployeeTransfer: EmployeeTransfer.objects.create(company=foreign, employee=foreign_employee, effective_date=date(2026,7,1)),
            Promotion: Promotion.objects.create(company=foreign, employee=foreign_employee, old_title="Engineer", new_title="Lead", effective_date=date(2026,7,1)),
            OffboardingChecklist: OffboardingChecklist.objects.create(company=foreign, employee=foreign_employee, last_working_day=date(2026,7,1), reason="RESIGNATION"),
        }
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])
        request = RequestFactory().get("/admin/")
        request.user = self.user
        for model in (HiringCandidate, JobOffer, EmployeeTransfer, Promotion, OffboardingChecklist):
            registered = admin.site._registry[model]
            self.assertFalse(registered.has_import_permission(request))
            self.assertIn("status", registered.get_readonly_fields(request))
            company_field = registered.formfield_for_foreignkey(model._meta.get_field("company"), request)
            self.assertEqual(list(company_field.queryset.values_list("pk", flat=True)), [self.company.pk])
            self.assertNotIn(foreign_records[model].pk, registered.get_queryset(request).values_list("pk", flat=True))
            self._grant("change_" + model._meta.model_name)
            self.client.force_login(self.user)
            response = self.client.get("/admin/payroll/" + model._meta.model_name + "/" + str(foreign_records[model].pk) + "/change/")
            self.assertNotEqual(response.status_code, 200)
        self.assertIn(candidate.pk, admin.site._registry[HiringCandidate].get_queryset(request).values_list("pk", flat=True))

    def test_admin_save_cannot_mutate_another_company(self):
        from company.models import Company
        foreign = Company.objects.create(name="Other offer company")
        offer = self._offer()
        offer.company = foreign
        request = RequestFactory().post("/admin/")
        request.user = self.user
        self._grant("change_joboffer")
        with self.assertRaises(PermissionDenied):
            admin.site._registry[JobOffer].save_model(request, offer, None, True)
