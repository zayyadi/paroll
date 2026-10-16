"""Registration proof cannot reverse an approved employment/access decision."""
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from accounting.models import DisciplinaryCase, DisciplinarySanction
from approvals.services import submit_approval, decide_approval
from company.models import Company
from tests.approval_helpers import approval_user


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
class DisabledRegistrationActivationTests(TestCase):
    def setUp(self):
        cache.clear()
        self.company = Company.objects.create(name="Activation permission tests")
        self.user = get_user_model().objects.create_user(email="terminated@example.test", password="StrongPass123!", company=self.company, active_company=self.company)
        permissions = ["accounting.change_disciplinarycase", "accounting.change_disciplinarysanction", "accounting.review_panel_disciplinarycase"]
        maker = approval_user(self.company, permissions)
        checker = approval_user(self.company, permissions)
        reporter = approval_user(self.company)
        case = DisciplinaryCase.objects.create(company=self.company, respondent=self.user, reporter=reporter, allegation_summary="Established employment decision", allegation_details="Approved evidence", violation_level="LEVEL_3")
        request = case.decide(finding="SUBSTANTIATED", decided_by=maker, rationale="Approved finding", approval_actor=maker)
        decide_approval(approval=request, actor=checker)
        case.refresh_from_db()
        sanction = DisciplinarySanction.objects.create(case=case, created_by=maker, sanction_type="TERMINATION", effective_date="2020-01-01", rationale="Approved termination")
        request = submit_approval(source=sanction, action="discipline.sanction", requester=maker)
        decide_approval(approval=request, actor=checker)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)
        self.assertEqual(self.user.employee_user.status, "terminated")

    def test_valid_registration_token_does_not_reverse_termination(self):
        token = default_token_generator.make_token(self.user)
        response = self.client.get(reverse("users:activate", kwargs={"uidb64": urlsafe_base64_encode(force_bytes(self.user.pk)), "token": token}))
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)
        self.assertEqual(response.status_code, 400)

    def test_valid_registration_otp_does_not_reverse_termination(self):
        cache.set(f"registration_otp_{self.user.email}", "654321", timeout=600)
        self.client.post(reverse("users:verify_registration_otp", kwargs={"email": self.user.email}), {"otp":"654321"})
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)

    def test_registration_resend_does_not_issue_proof_for_terminated_user(self):
        self.client.post(reverse("users:resend_registration_activation", kwargs={"email":self.user.email}))
        self.assertIsNone(cache.get(f"registration_otp_{self.user.email}"))
        self.assertEqual(len(mail.outbox), 0)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
class PendingRegistrationLifecycleTests(TestCase):
    def setUp(self):
        cache.clear()

    def register(self, email="new-registration@example.test"):
        response = self.client.post(reverse("users:register"), {
            "email":email, "first_name":"New", "last_name":"Registration",
            "password1":"StrongPass123!", "password2":"StrongPass123!",
        })
        self.assertEqual(response.status_code, 302)
        return get_user_model().objects.get(email=email)

    def test_real_registration_otp_completes_only_pending_state(self):
        user = self.register()
        self.assertFalse(user.is_active)
        self.assertTrue(user.registration_pending)
        otp = cache.get(f"registration_otp_{user.email}")
        self.assertIsNotNone(otp)
        response = self.client.post(reverse("users:verify_registration_otp", kwargs={"email":user.email}), {"otp":otp})
        self.assertEqual(response.status_code, 302)
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertFalse(user.registration_pending)

    def test_completed_registration_token_cannot_reactivate_disabled_account(self):
        user = self.register()
        token = default_token_generator.make_token(user)
        url = reverse("users:activate", kwargs={"uidb64":urlsafe_base64_encode(force_bytes(user.pk)), "token":token})
        self.assertEqual(self.client.get(url).status_code, 302)
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertFalse(user.registration_pending)
        # A security disable before first login must not reuse signup proof.
        user.is_active = False
        user.save(update_fields=["is_active"])
        self.assertTrue(default_token_generator.check_token(user, token))
        self.assertEqual(self.client.get(url).status_code, 400)
        user.refresh_from_db()
        self.assertFalse(user.is_active)

    def test_provisioned_inactive_user_cannot_issue_registration_proof(self):
        user = get_user_model().objects.create_user(email="provisioned@example.test", password="StrongPass123!", is_active=False)
        self.assertFalse(user.registration_pending)
        self.client.post(reverse("users:resend_registration_activation", kwargs={"email":user.email}))
        self.assertIsNone(cache.get(f"registration_otp_{user.email}"))
        self.assertEqual(len(mail.outbox), 0)

    def test_completed_offboarding_blocks_even_still_pending_signup(self):
        from payroll.services.offboarding_service import initiate_offboarding, complete_task
        from tests.approval_helpers import approve_source
        user = self.register()
        maker = approval_user(user.company, ["payroll.change_offboardingchecklist"])
        checklist = initiate_offboarding(employee=user.employee_user, initiated_by=maker, last_working_day="2020-01-01", reason="RESIGNATION")
        for task in checklist.tasks.all():
            complete_task(task=task, completed_by=maker)
        checklist.refresh_from_db()
        approve_source(checklist, "offboarding.complete", maker=maker)
        otp = cache.get(f"registration_otp_{user.email}")
        self.client.post(reverse("users:verify_registration_otp", kwargs={"email":user.email}), {"otp":otp})
        user.refresh_from_db()
        self.assertFalse(user.is_active)
