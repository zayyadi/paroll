"""A canonical close emits one complete business audit record."""
from datetime import date

from django.test import TestCase
from django.contrib.contenttypes.models import ContentType

from accounting.tests import test_canonical_approval_policies as policy_fixtures
from accounting.models import AccountingAuditTrail, FiscalYear
from accounting.tests.fixtures import JournalFactory
from accounting.utils import close_accounting_period, close_fiscal_year
from accounting.middleware import set_audit_user, set_audit_metadata
from approvals.services import decide_approval


class ClosureAuditOwnershipTests(TestCase):
    setUp = policy_fixtures.CanonicalAccountingPolicyTests.setUp
    policy = policy_fixtures.CanonicalAccountingPolicyTests.policy

    def test_canonical_closures_record_one_checker_reason_metadata_and_transition(self):
        period = JournalFactory.create_posted_journal(user=self.maker).period
        year = FiscalYear.objects.create(
            company=self.company,
            year=2028,
            name="Single audit year",
            start_date=date(2028, 1, 1),
            end_date=date(2028, 12, 31),
        )
        cases = [
            (
                period,
                close_accounting_period,
                "accounting.period.close",
                "accounting.change_accountingperiod",
                AccountingAuditTrail.ActionType.CLOSE_PERIOD,
            ),
            (
                year,
                close_fiscal_year,
                "accounting.year.close",
                "accounting.change_fiscalyear",
                AccountingAuditTrail.ActionType.CLOSE_FISCAL_YEAR,
            ),
        ]
        try:
            for source, operation, key, permission, action in cases:
                with self.subTest(action=action):
                    self.policy(key, permission)
                    request = operation(
                        source, self.maker, reason="Independent scheduled close"
                    )
                    request = decide_approval(approval=request, actor=self.first)
                    # HTTP metadata belongs to the decision request, while the
                    # business actor is the actual independent final checker.
                    set_audit_user(self.maker)
                    set_audit_metadata("203.0.113.10", "Approval review browser")
                    with self.captureOnCommitCallbacks(execute=True):
                        decide_approval(approval=request, actor=self.second)
                    audit = AccountingAuditTrail.objects.get(
                        content_type=ContentType.objects.get_for_model(source),
                        object_id=source.pk,
                        action=action,
                    )
                    self.assertEqual(audit.user_id, self.second.pk)
                    self.assertEqual(audit.reason, "Independent scheduled close")
                    self.assertEqual(audit.ip_address, "203.0.113.10")
                    self.assertEqual(audit.user_agent, "Approval review browser")
                    self.assertEqual(audit.changes["is_closed"]["new"], "True")
        finally:
            set_audit_user(None)
            set_audit_metadata(None, None)
