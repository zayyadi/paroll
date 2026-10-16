from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError, PermissionDenied
from django.test import TestCase
from django.urls import reverse

from approvals.models import ApprovalPolicy, ApprovalRequest
from approvals.services import decide_approval, submit_approval
from inventory.models import Customer, InventoryDocument, StockCount
from inventory.tests import test_inventory_core as core_fixtures
from inventory.tests.approval_fixtures import approved_inventory_operation


class InventoryApprovalRouteTests(TestCase):
    setUp = core_fixtures.InventoryCoreTests.setUp
    _create_accounts = core_fixtures.InventoryCoreTests._create_accounts

    def actor(self, name):
        user = get_user_model().objects.create_user(
            email=name + "@routes.test",
            password="x",
            company=self.company_a,
            active_company=self.company_a,
        )
        user.user_permissions.add(
            *Permission.objects.filter(
                content_type__app_label="inventory",
                codename__in=[
                    "add_inventorydocument",
                    "change_inventorydocument",
                    "change_stockcount",
                ],
            )
        )
        return user

    def policy(self, action):
        ApprovalPolicy.objects.create(
            company=self.company_a,
            action=action,
            stages=[
                {"permission": "inventory.change_inventorydocument"},
                {"permission": "inventory.change_inventorydocument"},
            ],
        )

    def approval_from(self, response):
        self.assertEqual(response.status_code, 302, response.content[:1000])
        self.assertTrue(response.url.startswith("/approvals/"), response.url)
        return ApprovalRequest.objects.get(
            pk=int(response.url.strip("/").split("/")[-1])
        )

    def login(self, user):
        self.client.force_login(user)

    def stock_document(self, quantity="3"):
        from inventory.services import post_opening_stock

        return approved_inventory_operation(post_opening_stock)(
            company=self.company_a,
            item=self.item,
            location=self.main_location,
            quantity=Decimal(quantity),
            unit_cost=Decimal("10"),
        )

    def test_document_route_keeps_multistage_pending_and_blocks_maker(self):
        maker, first, second = [
            self.actor("document-" + name) for name in ("maker", "first", "second")
        ]
        document = InventoryDocument.objects.create(
            company=self.company_a,
            document_type="ADJUSTMENT",
            requested_by=maker,
            status="PENDING_APPROVAL",
        )
        self.policy("inventory.document.approve")
        url = reverse("inventory:document_approve", args=[document.pk])
        self.login(first)
        request = self.approval_from(self.client.post(url))
        self.assertEqual(request.status, "PENDING")
        self.assertEqual(request.current_stage, 1)
        document.refresh_from_db()
        self.assertEqual(document.status, "PENDING_APPROVAL")
        self.login(maker)
        self.assertEqual(self.client.post(url).status_code, 403)
        self.login(second)
        self.assertEqual(self.approval_from(self.client.post(url)).status, "APPROVED")
        document.refresh_from_db()
        self.assertEqual(document.status, "APPROVED")

    def test_rejection_requires_independent_actor_reason_and_atomic_callback(self):
        maker, checker = [self.actor("reject-" + name) for name in ("maker", "checker")]
        document = InventoryDocument.objects.create(
            company=self.company_a,
            document_type="ADJUSTMENT",
            requested_by=maker,
            status="PENDING_APPROVAL",
        )
        submit_approval(
            source=document, action="inventory.document.approve", requester=maker
        )
        url = reverse("inventory:document_reject", args=[document.pk])
        self.login(checker)
        self.assertEqual(self.client.post(url).status_code, 400)
        document.refresh_from_db()
        self.assertEqual(document.status, "PENDING_APPROVAL")
        self.login(maker)
        self.assertEqual(
            self.client.post(url, {"reason": "not valid"}).status_code, 403
        )
        self.login(checker)
        request = self.approval_from(
            self.client.post(url, {"reason": "Wrong warehouse"})
        )
        self.assertEqual(request.status, "REJECTED")
        self.assertEqual(request.decisions.get().comment, "Wrong warehouse")
        document.refresh_from_db()
        self.assertEqual(document.status, "CANCELLED")

    def test_stock_count_multistage_route_and_pending_post(self):
        maker, first, second = [
            self.actor("count-" + name) for name in ("maker", "first", "second")
        ]
        count = StockCount.objects.create(
            company=self.company_a, location=self.main_location, status="COUNTED"
        )
        count.lines.create(item=self.item, system_quantity=0, counted_quantity=0)
        self.policy("inventory.stock_count.approve")
        url = reverse("inventory:stock_count_approve", args=[count.pk])
        post_url = reverse("inventory:stock_count_post", args=[count.pk])
        self.login(maker)
        self.assertEqual(self.approval_from(self.client.post(url)).status, "PENDING")
        self.login(first)
        self.assertEqual(self.approval_from(self.client.post(url)).status, "PENDING")
        count.refresh_from_db()
        self.assertEqual(count.status, "COUNTED")
        self.assertEqual(self.client.post(post_url).status_code, 400)
        self.login(second)
        self.assertEqual(self.approval_from(self.client.post(url)).status, "APPROVED")
        self.login(maker)
        posting = self.approval_from(self.client.post(post_url))
        self.assertEqual(posting.status, "PENDING")
        count.refresh_from_db()
        self.assertEqual(count.status, "APPROVED")
        decide_approval(approval=posting, actor=first)
        count.refresh_from_db()
        self.assertEqual(count.status, "POSTED")

    def test_variance_route_is_independent_and_company_scoped(self):
        maker, checker = [
            self.actor("variance-" + name) for name in ("maker", "checker")
        ]
        count = StockCount.objects.create(
            company=self.company_a, location=self.main_location, status="COUNTED"
        )
        line = count.lines.create(item=self.item, system_quantity=0, counted_quantity=1)
        url = reverse("inventory:stock_variance_approve", args=[count.pk, line.pk])
        self.login(maker)
        self.approval_from(self.client.post(url))
        line.refresh_from_db()
        self.assertEqual(line.investigation_status, "PENDING")
        self.assertEqual(self.client.post(url).status_code, 403)
        self.login(checker)
        self.assertEqual(self.approval_from(self.client.post(url)).status, "APPROVED")
        line.refresh_from_db()
        self.assertEqual(line.investigation_status, "APPROVED")
        checker.active_company = self.company_b
        checker.company = self.company_b
        checker.save()
        self.login(checker)
        self.assertEqual(self.client.post(url).status_code, 404)

    def test_form_intents_have_fresh_keys_and_bank_reference_required(self):
        self.login(self.actor("form-maker"))
        first = self.client.get(reverse("inventory:opening_stock"))
        second = self.client.get(reverse("inventory:opening_stock"))
        self.assertEqual(first.status_code, 200)
        self.assertNotEqual(
            first.context["approval_key"], second.context["approval_key"]
        )
        self.assertContains(first, 'name="_approval_key"')
        from django.template.loader import render_to_string

        html = render_to_string(
            "payroll/bank_payment_generate.html", {"runs": [], "bank_codes": {}}
        )
        self.assertIn('name="reference" required', html)

    def test_reversal_is_pending_and_final_effect_balances_stock_and_ledger(self):
        from inventory.services import get_stock_on_hand
        from accounting.models import Journal

        original = self.stock_document()
        maker, checker = [
            self.actor("reverse-" + name) for name in ("maker", "checker")
        ]
        self.login(maker)
        request = self.approval_from(
            self.client.post(
                reverse("inventory:document_reverse", args=[original.pk]),
                {"reason": "Opening import correction"},
            )
        )
        self.assertEqual(get_stock_on_hand(self.item, self.main_location), Decimal("3"))
        self.assertEqual(Journal.objects.filter(company=self.company_a).count(), 1)
        decide_approval(approval=request, actor=checker)
        original.refresh_from_db()
        self.assertEqual(original.status, "CANCELLED")
        self.assertEqual(get_stock_on_hand(self.item, self.main_location), Decimal("0"))
        self.assertEqual(Journal.objects.filter(company=self.company_a).count(), 2)
        self.accounts["inventory"].refresh_from_db()
        self.assertEqual(self.accounts["inventory"].current_balance, Decimal("0"))
        reversal = InventoryDocument.objects.get(
            company=self.company_a, reference="REV-" + str(original.pk)
        )
        self.assertEqual(reversal.journal.approval_request_id, request.pk)
        self.assertEqual(reversal.journal.posted_by_id, checker.pk)

    def test_reversal_failure_rolls_back_decisions_and_all_effects(self):
        from inventory.services import post_sales_invoice
        from accounting.models import Journal

        maker, checker = [
            self.actor("rollback-" + name) for name in ("maker", "checker")
        ]
        original = self.stock_document()
        self.login(maker)
        request = self.approval_from(
            self.client.post(
                reverse("inventory:document_reverse", args=[original.pk]),
                {"reason": "Opening correction"},
            )
        )
        self.category.sales_revenue_account = self.accounts["sales"]
        self.category.cogs_account = self.accounts["cogs"]
        self.category.save()
        customer = Customer.objects.create(
            company=self.company_a,
            name="After-submission buyer",
            receivable_account=self.accounts["receivable"],
        )
        approved_inventory_operation(post_sales_invoice)(
            company=self.company_a,
            customer=customer,
            location=self.main_location,
            lines=[
                {
                    "item": self.item,
                    "quantity": Decimal("2"),
                    "unit_price": Decimal("30"),
                }
            ],
        )
        before = (
            InventoryDocument.objects.count(),
            Journal.objects.count(),
            self.item.stock_movements.count(),
        )
        with self.assertRaises(ValidationError):
            decide_approval(approval=request, actor=checker)
        self.assertEqual(
            (
                InventoryDocument.objects.count(),
                Journal.objects.count(),
                self.item.stock_movements.count(),
            ),
            before,
        )
        self.assertFalse(request.decisions.exists())
        request.refresh_from_db()
        self.assertEqual(request.status, "PENDING")
        original.refresh_from_db()
        self.assertEqual(original.status, "POSTED")

    def test_transfer_reversal_preserves_total_value_without_inventing_journals(self):
        from inventory.services import post_stock_transfer, get_stock_on_hand
        from accounting.models import Journal

        self.stock_document()
        transfer = approved_inventory_operation(post_stock_transfer)(
            company=self.company_a,
            item=self.item,
            from_location=self.main_location,
            to_location=self.branch_location,
            quantity=Decimal("2"),
        )
        maker, checker = [
            self.actor("transfer-" + name) for name in ("maker", "checker")
        ]
        self.login(maker)
        request = self.approval_from(
            self.client.post(
                reverse("inventory:document_reverse", args=[transfer.pk]),
                {"reason": "Wrong destination"},
            )
        )
        decide_approval(approval=request, actor=checker)
        self.assertEqual(get_stock_on_hand(self.item, self.main_location), Decimal("3"))
        self.assertEqual(
            get_stock_on_hand(self.item, self.branch_location), Decimal("0")
        )
        self.assertEqual(Journal.objects.filter(company=self.company_a).count(), 1)

    def test_vat_exposure_selects_extra_stage_and_tax_rule_change_stales_request(self):
        from inventory.services import post_sales_invoice
        from inventory.models import TaxJurisdiction, TaxRule
        from django.utils import timezone

        maker, checker = [self.actor("vat-" + name) for name in ("maker", "checker")]
        self.category.sales_revenue_account = self.accounts["sales"]
        self.category.cogs_account = self.accounts["cogs"]
        self.category.save()
        self.item.default_vat_rate = Decimal("20")
        self.item.save()
        self.stock_document()
        customer = Customer.objects.create(
            company=self.company_a,
            name="Tax review buyer",
            receivable_account=self.accounts["receivable"],
        )
        ApprovalPolicy.objects.create(
            company=self.company_a,
            action="inventory.sales_invoice",
            currency="NGN",
            minimum_amount=Decimal("110"),
            stages=[
                {"permission": "inventory.change_inventorydocument"},
                {"permission": "inventory.change_inventorydocument"},
            ],
        )
        request = post_sales_invoice(
            company=self.company_a,
            customer=customer,
            location=self.main_location,
            lines=[
                {
                    "item": self.item,
                    "quantity": Decimal("1"),
                    "unit_price": Decimal("100"),
                }
            ],
            vat_output_account=self.accounts["vat_output"],
            approval_actor=maker,
        )
        self.assertEqual(Decimal(request.policy_snapshot["amount"]), Decimal("120"))
        self.assertEqual(len(request.policy_snapshot["stages"]), 2)
        jurisdiction = TaxJurisdiction.objects.create(
            company=self.company_a, name="Rule change", code="RC"
        )
        TaxRule.objects.create(
            company=self.company_a,
            jurisdiction=jurisdiction,
            tax_type="VAT",
            transaction_type="SALE",
            rate=Decimal("25"),
            effective_from=timezone.now().date(),
        )
        with self.assertRaises(ValidationError):
            decide_approval(approval=request, actor=checker)
        self.assertFalse(request.decisions.exists())

    def test_payment_allocation_stays_pending_until_independent_approval(self):
        from inventory.services import (
            post_sales_invoice,
            post_customer_payment,
            allocate_customer_payment,
        )
        from inventory.models import (
            CustomerPayment,
            SalesInvoice,
            CustomerPaymentAllocation,
        )

        maker, checker = [
            self.actor("allocate-" + name) for name in ("maker", "checker")
        ]
        self.category.sales_revenue_account = self.accounts["sales"]
        self.category.cogs_account = self.accounts["cogs"]
        self.category.save()
        self.stock_document()
        customer = Customer.objects.create(
            company=self.company_a,
            name="Allocation buyer",
            receivable_account=self.accounts["receivable"],
        )
        invoice_doc = approved_inventory_operation(post_sales_invoice)(
            company=self.company_a,
            customer=customer,
            location=self.main_location,
            lines=[
                {
                    "item": self.item,
                    "quantity": Decimal("1"),
                    "unit_price": Decimal("100"),
                }
            ],
        )
        payment_doc = approved_inventory_operation(post_customer_payment)(
            company=self.company_a,
            customer=customer,
            cash_account=self.accounts["bank"],
            amount=Decimal("80"),
        )
        payment = CustomerPayment.objects.get(document=payment_doc)
        invoice = SalesInvoice.objects.get(document=invoice_doc)
        request = allocate_customer_payment(
            payment=payment, invoice=invoice, amount=Decimal("50"), approval_actor=maker
        )
        self.assertEqual(request.status, "PENDING")
        self.assertFalse(CustomerPaymentAllocation.objects.exists())
        invoice.refresh_from_db()
        self.assertEqual(invoice.paid_amount, Decimal("0"))
        with self.assertRaises(PermissionDenied):
            decide_approval(approval=request, actor=maker)
        decide_approval(approval=request, actor=checker)
        invoice.refresh_from_db()
        self.assertEqual(invoice.paid_amount, Decimal("50"))
        self.assertEqual(CustomerPaymentAllocation.objects.get().amount, Decimal("50"))

    def test_financial_children_cannot_be_forged_edited_imported_or_deleted(self):
        from inventory.services import post_customer_payment
        from inventory.models import CustomerPayment, CustomerPaymentAllocation
        from inventory.admin import CustomerPaymentResource
        from django.contrib import admin
        from django.test import RequestFactory
        from tablib import Dataset

        maker = self.actor("guard-maker")
        customer = Customer.objects.create(
            company=self.company_a,
            name="Guarded buyer",
            receivable_account=self.accounts["receivable"],
        )
        document = approved_inventory_operation(post_customer_payment)(
            company=self.company_a,
            customer=customer,
            cash_account=self.accounts["bank"],
            amount=Decimal("70"),
        )
        payment = CustomerPayment.objects.get(document=document)
        self.assertIsNotNone(payment.approval_request_id)
        with self.assertRaises(ValidationError):
            CustomerPayment.objects.create(
                company=self.company_a,
                customer=customer,
                document=document,
                cash_account=self.accounts["bank"],
                amount=Decimal("1"),
            )
        with self.assertRaises(ValidationError):
            CustomerPayment.objects.filter(pk=payment.pk).update(amount=Decimal("1"))
        payment.amount = Decimal("1")
        with self.assertRaises(ValidationError):
            payment.save()
        with self.assertRaises(ValidationError):
            payment.delete()
        request = RequestFactory().get("/admin/inventory/customerpayment/")
        request.user = maker
        model_admin = admin.site._registry[CustomerPayment]
        self.assertFalse(model_admin.has_import_permission(request))
        self.assertFalse(model_admin.has_change_permission(request, payment))
        self.assertFalse(model_admin.has_add_permission(request))
        data = Dataset(headers=["id", "amount"])
        data.append([payment.pk, "1"])
        result = CustomerPaymentResource().import_data(data, dry_run=True)
        self.assertTrue(result.has_errors() or result.has_validation_errors())
        payment.refresh_from_db()
        self.assertEqual(payment.amount, Decimal("70"))

    def test_zero_sales_price_uses_posting_default_for_threshold(self):
        from inventory.services import post_sales_invoice

        maker = self.actor("default-price-maker")
        self.category.sales_revenue_account = self.accounts["sales"]
        self.category.cogs_account = self.accounts["cogs"]
        self.category.save()
        self.item.default_sales_price = Decimal("100")
        self.item.save()
        self.stock_document()
        customer = Customer.objects.create(
            company=self.company_a,
            name="Default price buyer",
            receivable_account=self.accounts["receivable"],
        )
        ApprovalPolicy.objects.create(
            company=self.company_a,
            action="inventory.sales_invoice",
            currency="NGN",
            minimum_amount=Decimal("50"),
            stages=[
                {"permission": "inventory.change_inventorydocument"},
                {"permission": "inventory.change_inventorydocument"},
            ],
        )
        request = post_sales_invoice(
            company=self.company_a,
            customer=customer,
            location=self.main_location,
            lines=[
                {
                    "item": self.item,
                    "quantity": Decimal("1"),
                    "unit_price": Decimal("0"),
                }
            ],
            approval_actor=maker,
        )
        self.assertEqual(Decimal(request.policy_snapshot["amount"]), Decimal("100"))
        self.assertEqual(len(request.policy_snapshot["stages"]), 2)

    def test_negative_adjustment_cannot_supply_cheap_cost_to_bypass_policy(self):
        from inventory.services import post_inventory_adjustment

        maker = self.actor("negative-cost-maker")
        self.stock_document()
        ApprovalPolicy.objects.create(
            company=self.company_a,
            action="inventory.adjustment",
            currency="NGN",
            minimum_amount=Decimal("5"),
            stages=[
                {"permission": "inventory.change_inventorydocument"},
                {"permission": "inventory.change_inventorydocument"},
            ],
        )
        request = post_inventory_adjustment(
            company=self.company_a,
            item=self.item,
            location=self.main_location,
            quantity_delta=Decimal("-1"),
            unit_cost=Decimal("0.01"),
            approval_actor=maker,
        )
        self.assertEqual(Decimal(request.policy_snapshot["amount"]), Decimal("10"))
        self.assertEqual(len(request.policy_snapshot["stages"]), 2)

    def test_tax_jurisdiction_state_change_invalidates_reviewed_value(self):
        from inventory.services import post_sales_invoice
        from inventory.models import TaxJurisdiction, TaxRule
        from django.utils import timezone

        maker = self.actor("jurisdiction-maker")
        checker = self.actor("jurisdiction-checker")
        self.category.sales_revenue_account = self.accounts["sales"]
        self.category.cogs_account = self.accounts["cogs"]
        self.category.save()
        self.stock_document()
        jurisdiction = TaxJurisdiction.objects.create(
            company=self.company_a,
            name="Selected tax",
            code="SELECT",
            is_default=True,
            is_active=True,
        )
        TaxRule.objects.create(
            company=self.company_a,
            jurisdiction=jurisdiction,
            tax_type="VAT",
            transaction_type="SALE",
            rate=Decimal("20"),
            effective_from=timezone.now().date(),
        )
        customer = Customer.objects.create(
            company=self.company_a,
            name="Jurisdiction buyer",
            receivable_account=self.accounts["receivable"],
        )
        request = post_sales_invoice(
            company=self.company_a,
            customer=customer,
            location=self.main_location,
            lines=[
                {
                    "item": self.item,
                    "quantity": Decimal("1"),
                    "unit_price": Decimal("100"),
                }
            ],
            vat_output_account=self.accounts["vat_output"],
            approval_actor=maker,
        )
        jurisdiction.is_default = False
        jurisdiction.save()
        with self.assertRaises(ValidationError):
            decide_approval(approval=request, actor=checker)
        self.assertFalse(request.decisions.exists())
