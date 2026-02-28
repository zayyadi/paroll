from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase

from accounting.mixins import JournalApprovalMixin
from accounting.models import AccountingPeriod, FiscalYear, Journal


class JournalApprovalMixinTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            email="mixin-admin@test.com",
            password="testpass123",
            first_name="Mixin",
            last_name="Admin",
        )
        self.fiscal_year = FiscalYear.objects.create(
            year=2026,
            name="FY 2026",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            is_active=True,
        )
        self.period = AccountingPeriod.objects.create(
            fiscal_year=self.fiscal_year,
            period_number=1,
            name="January 2026",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            is_active=True,
            is_closed=False,
        )
        self.journal = Journal.objects.create(
            description="Mixin permission resolution test",
            date=date(2026, 1, 15),
            period=self.period,
            status=Journal.JournalStatus.PENDING_APPROVAL,
            created_by=self.user,
        )

    def test_form_view_style_resolution_works_without_get_object(self):
        class DummyApprovalView(JournalApprovalMixin):
            permission_object_model = Journal

        view = DummyApprovalView()
        view.request = type("Request", (), {"user": self.user})()
        view.kwargs = {"pk": self.journal.pk}

        resolved = view.get_permission_object()
        self.assertEqual(resolved.pk, self.journal.pk)
        self.assertTrue(view.test_func())

    def test_missing_configuration_raises_helpful_error(self):
        class BrokenApprovalView(JournalApprovalMixin):
            permission_object_model = None

        view = BrokenApprovalView()
        view.request = type("Request", (), {"user": self.user})()
        view.kwargs = {"pk": self.journal.pk}

        with self.assertRaisesMessage(
            AttributeError,
            "must define get_object() or permission_object_model",
        ):
            view.get_permission_object()
