"""A business operation has one policy across utilities, models and API."""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from accounting.tests.fixtures import JournalFactory, UserFactory
from accounting.models import AccountingPeriod, FiscalYear
from approvals.models import ApprovalPolicy, ApprovalRequest
from approvals.services import decide_approval
from approvals.registry import registered_actions


class CanonicalAccountingPolicyTests(TestCase):
    def setUp(self):
        self.maker = UserFactory.create_accountant()
        self.maker.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="accounting", codename="change_fiscalyear"
            )
        )
        self.company = self.maker.company
        self.first = get_user_model().objects.create_user(
            email="first-designated@test.local",
            password="x",
            company=self.company,
            active_company=self.company,
        )
        self.second = get_user_model().objects.create_user(
            email="second-designated@test.local",
            password="x",
            company=self.company,
            active_company=self.company,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.maker)

    def policy(self, action, permission):
        ApprovalPolicy.objects.create(
            company=self.company,
            action=action,
            stages=[
                {"permission": permission, "approver_ids": [self.first.pk]},
                {"permission": permission, "approver_ids": [self.second.pk]},
            ],
        )

    def test_model_reversal_cannot_bypass_canonical_two_stage_policy(self):
        journal = JournalFactory.create_posted_journal(user=self.maker)
        self.policy("accounting.journal.reverse", "accounting.change_journal")
        request = journal.reverse(self.maker, "Policy consistency")
        self.assertEqual(request.action, "accounting.journal.reverse")
        self.assertEqual(len(request.policy_snapshot["stages"]), 2)
        request = decide_approval(approval=request, actor=self.first)
        journal.refresh_from_db()
        self.assertEqual(journal.status, "POSTED")
        request = decide_approval(approval=request, actor=self.second)
        journal.refresh_from_db()
        self.assertEqual(journal.status, "REVERSED")
        self.assertEqual(request.status, "APPROVED")

    def test_api_period_close_uses_canonical_policy_and_returns_pending(self):
        journal = JournalFactory.create_posted_journal(user=self.maker)
        period = journal.period
        self.policy("accounting.period.close", "accounting.change_accountingperiod")
        response = self.client.post(
            reverse("api:v1:accounting-period-close", args=[period.pk]),
            {},
            format="json",
        )
        self.assertEqual(response.status_code, 202, response.data)
        request = ApprovalRequest.objects.get(pk=response.data["approval_id"])
        self.assertEqual(request.action, "accounting.period.close")
        decide_approval(approval=request, actor=self.first)
        period.refresh_from_db()
        self.assertFalse(period.is_closed)
        decide_approval(approval=request, actor=self.second)
        period.refresh_from_db()
        self.assertTrue(period.is_closed)
        self.assertEqual(period.closed_by_id, self.second.pk)

    def test_api_reversal_uses_canonical_policy_and_designated_checker(self):
        journal = JournalFactory.create_posted_journal(user=self.maker)
        self.policy("accounting.journal.reverse", "accounting.change_journal")
        response = self.client.post(
            reverse("api:v1:journal-reverse", args=[journal.pk]),
            {"reason": "Designated checker reversal"},
            format="json",
        )
        self.assertEqual(response.status_code, 202, response.data)
        request = ApprovalRequest.objects.get(pk=response.data["approval_id"])
        self.assertEqual(request.action, "accounting.journal.reverse")
        request = decide_approval(approval=request, actor=self.first)
        request = decide_approval(approval=request, actor=self.second)
        self.assertEqual(request.status, "APPROVED")
        self.assertFalse(self.second.has_perm("accounting.change_journal"))

    def test_alias_policy_keys_are_not_exposed_as_separate_actions(self):
        actions = registered_actions()
        for key in (
            "accounting.journal.model_reverse",
            "accounting.period.model_close",
            "accounting.year.model_close",
        ):
            self.assertNotIn(key, actions)
        self.assertIn("accounting.year.close", actions)

    def test_api_year_close_uses_the_same_canonical_year_policy(self):
        from datetime import date

        year = FiscalYear.objects.create(
            company=self.company,
            year=2027,
            name="Policy-only fiscal year",
            start_date=date(2027, 1, 1),
            end_date=date(2027, 12, 31),
        )
        self.policy("accounting.year.close", "accounting.change_fiscalyear")
        response = self.client.post(
            reverse("api:v1:fiscal-year-close", args=[year.pk]), {}, format="json"
        )
        self.assertEqual(response.status_code, 202, response.data)
        request = ApprovalRequest.objects.get(pk=response.data["approval_id"])
        self.assertEqual(request.action, "accounting.year.close")
        decide_approval(approval=request, actor=self.first)
        year.refresh_from_db()
        self.assertFalse(year.is_closed)
        decide_approval(approval=request, actor=self.second)
        year.refresh_from_db()
        self.assertTrue(year.is_closed)

    def test_designated_grant_is_not_a_legacy_role_outside_valid_execution(self):
        from accounting.permissions import can_reverse_journal, can_close_period

        journal = JournalFactory.create_posted_journal(user=self.maker)
        self.assertFalse(can_reverse_journal(self.second, journal))
        self.assertFalse(can_close_period(self.second, journal.period))

    def test_trusted_grant_requires_actual_final_actor_not_other_legacy_accountant(
        self,
    ):
        from accounting.permissions import can_reverse_journal, can_close_period
        from approvals.registry import ApprovalAction, register_action, _actions
        from approvals.services import submit_approval

        journal = JournalFactory.create_posted_journal(user=self.maker)
        observed = {}

        def verify(source, actor, payload):
            observed["checker"] = can_reverse_journal(actor, journal)
            observed["other_legacy_actor"] = can_reverse_journal(self.maker, journal)
            observed["period_checker"] = can_close_period(actor, source)

        key = "test.final_checker.company"
        register_action(
            ApprovalAction(
                key=key,
                model_label="accounting.AccountingPeriod",
                permission="accounting.change_accountingperiod",
                apply=verify,
            )
        )
        try:
            ApprovalPolicy.objects.create(
                company=self.company,
                action=key,
                stages=[
                    {
                        "permission": "accounting.change_accountingperiod",
                        "approver_ids": [self.second.pk],
                    }
                ],
            )
            request = submit_approval(
                source=journal.period, action=key, requester=self.maker
            )
            decide_approval(approval=request, actor=self.second)
            self.assertTrue(observed["checker"])
            self.assertTrue(observed["period_checker"])
            self.assertFalse(observed["other_legacy_actor"])
        finally:
            _actions.pop(key, None)
