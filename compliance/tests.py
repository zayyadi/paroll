"""Tests for the NDPA data-subject request workflow (P1-8).

Gap #8 of docs/world_class_employee_management_research_2026-10-14.md: NDPA
rights need request intake, identity verification, approve/fulfil/reject states
and export/erasure actions that respect retention rules.
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from company.models import Company
from compliance.models import DataRetentionPolicy, DataSubjectRequest
from compliance import services


class DSRFixture(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="DSR Co")
        self.user = get_user_model().objects.create_user(
            email="subject@example.com",
            password="password123",
            first_name="Ada",
            last_name="Lovelace",
            company=self.company,
            active_company=self.company,
        )
        self.employee = self.user.employee_user
        self.employee.company = self.company
        self.employee.save()
        self.admin = get_user_model().objects.create_user(
            email="dpo@example.com",
            password="password123",
            company=self.company,
            active_company=self.company,
        )

    def _submit(self, request_type="access", **overrides):
        defaults = dict(
            company=self.company,
            request_type=request_type,
            subject_email=self.user.email,
            subject=self.user,
            description="Please provide my data.",
        )
        defaults.update(overrides)
        return services.submit_request(**defaults)


class IntakeTests(DSRFixture):
    def test_submit_defaults_to_submitted(self):
        request = self._submit()
        self.assertEqual(request.status, DataSubjectRequest.Status.SUBMITTED)
        self.assertEqual(request.subject, self.user)

    def test_submit_sets_a_30_day_deadline(self):
        request = self._submit()
        expected = request.received_at + timedelta(
            days=services.RESPONSE_DEADLINE_DAYS
        )
        self.assertEqual(request.due_at, expected)

    def test_unknown_request_type_rejected(self):
        with self.assertRaises(ValidationError):
            self._submit(request_type="telepathy")

    def test_lifecycle_happy_path_for_access_export(self):
        request = self._submit(request_type="access")
        services.verify_request(request, actor=self.admin, note="ID checked")
        self.assertEqual(request.status, DataSubjectRequest.Status.VERIFIED)
        self.assertEqual(request.verified_by, self.admin)

        services.approve_request(request, actor=self.admin, note="OK")
        self.assertEqual(request.status, DataSubjectRequest.Status.APPROVED)

        services.fulfil_request(request, actor=self.admin)
        self.assertEqual(request.status, DataSubjectRequest.Status.FULFILLED)
        self.assertIsNotNone(request.fulfilled_at)
        # Export payload contains the subject's email.
        self.assertEqual(request.response["subject_email"], self.user.email)
        self.assertEqual(request.response["user"]["email"], self.user.email)

    def test_portability_export_is_json_safe(self):
        request = self._submit(request_type="portability")
        services.verify_request(request, actor=self.admin)
        services.approve_request(request, actor=self.admin)
        services.fulfil_request(request, actor=self.admin)
        self.assertEqual(request.response["request_type"], "portability")
        self.assertIn("exported_at", request.response)

    def test_reject_from_any_state_is_terminal(self):
        request = self._submit()
        services.reject_request(request, actor=self.admin, note="Not me")
        self.assertEqual(request.status, DataSubjectRequest.Status.REJECTED)
        with self.assertRaises(ValidationError):
            services.verify_request(request, actor=self.admin)

    def test_cannot_skip_verification(self):
        request = self._submit()
        with self.assertRaises(ValidationError):
            services.approve_request(request, actor=self.admin)

    def test_cannot_fulfil_without_approval(self):
        request = self._submit()
        services.verify_request(request, actor=self.admin)
        with self.assertRaises(ValidationError):
            services.fulfil_request(request, actor=self.admin)

    def test_rectification_fulfilment_records_acknowledgement(self):
        request = self._submit(request_type="rectification")
        services.verify_request(request, actor=self.admin)
        services.approve_request(request, actor=self.admin)
        services.fulfil_request(request, actor=self.admin)
        self.assertEqual(request.response["action"], "acknowledged")


class ErasureTests(DSRFixture):
    def _erase_request(self):
        request = self._submit(request_type="erasure")
        services.verify_request(request, actor=self.admin)
        services.approve_request(request, actor=self.admin)
        return request

    def test_erasure_anonymises_when_no_retention(self):
        request = self._erase_request()
        services.fulfil_request(request, actor=self.admin)
        self.user.refresh_from_db()
        self.employee.refresh_from_db()
        self.assertNotEqual(self.user.email, "subject@example.com")
        self.assertIn("erased", self.user.email)
        self.assertEqual(self.employee.first_name, "Redacted")

    def test_erasure_blocked_by_active_payroll_retention(self):
        DataRetentionPolicy.objects.create(
            company=self.company, record_type="PAYROLL", retention_days=2555
        )
        request = self._erase_request()
        with self.assertRaises(ValidationError):
            services.fulfil_request(request, actor=self.admin)
        request.refresh_from_db()
        # Still approved; erasure did not silently fulfil.
        self.assertEqual(request.status, DataSubjectRequest.Status.APPROVED)

    def test_erasure_blocked_by_tax_retention(self):
        DataRetentionPolicy.objects.create(
            company=self.company, record_type="TAX", retention_days=2555
        )
        self.assertTrue(
            services.erasure_blocked_by_retention(self.company)
        )

    def test_inactive_retention_policy_does_not_block(self):
        DataRetentionPolicy.objects.create(
            company=self.company,
            record_type="PAYROLL",
            retention_days=2555,
            is_active=False,
        )
        self.assertEqual(
            services.erasure_blocked_by_retention(self.company), []
        )

    def test_erasure_scopes_to_matching_email_when_subject_missing(self):
        request = self._submit(request_type="erasure")
        request.subject = None
        request.save()
        services.verify_request(request, actor=self.admin)
        services.approve_request(request, actor=self.admin)
        services.fulfil_request(request, actor=self.admin)
        self.user.refresh_from_db()
        self.assertIn("erased", self.user.email)
