from types import SimpleNamespace

from django.test import TestCase
from django.core.exceptions import ValidationError
from company.models import Company
from inventory.models import StockCount, StockCountLine
from accounting.models import Account
from approvals.registry import ApprovalAction
from approvals.services import _company
from approvals.proposals import object_company


class CompanyResolutionTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Resolver company")
        self.action = ApprovalAction(
            key="resolution.test",
            model_label="inventory.StockCountLine",
            permission="inventory.change_stockcount",
            apply=lambda *args: None,
        )

    def test_engine_and_references_resolve_the_same_owned_child(self):
        count = StockCount(company=self.company)
        line = StockCountLine(stock_count=count)
        self.assertEqual(_company(line, self.action), self.company)
        self.assertEqual(object_company(line), self.company)

    def test_explicit_adapter_company_takes_precedence(self):
        override = Company.objects.create(name="Explicit resolver company")
        action = ApprovalAction(
            key="resolution.override",
            model_label="inventory.StockCountLine",
            permission="inventory.change_stockcount",
            apply=lambda *args: None,
            company=lambda source: override,
        )
        source = StockCount(company=self.company)
        self.assertEqual(_company(source, action), override)

    def test_missing_ownership_fails_closed(self):
        with self.assertRaises(ValidationError):
            _company(StockCount(), self.action)

    def test_existing_account_payroll_and_run_relation_fallbacks_remain(self):
        owned = Account(company=self.company)
        for relation in ("account", "payroll", "payroll_run"):
            source = SimpleNamespace(
                _meta=SimpleNamespace(label_lower="test.reference"),
                company=None,
                **{relation: owned}
            )
            with self.subTest(relation=relation):
                self.assertEqual(_company(source, self.action), self.company)
