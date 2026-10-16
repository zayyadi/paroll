"""Inventory approvals gate commitments, movements and financial posting."""
from __future__ import annotations
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db import transaction
from decimal import Decimal, ROUND_HALF_UP
from approvals.registry import ApprovalAction, register_action
from approvals.proposals import (
    proposal_operation,
    proposal_snapshot,
    decode_value,
    _proposal_amount,
)
from approvals.permissions import require_company_authority
from approvals.services import current_execution, request_or_decide, submit_approval
from inventory import models, services


def inventory_exposure(source, payload):
    """Gross trade value includes VAT; withholding does not reduce authority."""
    values = decode_value(source.parameters, source.company)
    taxable_actions = {
        "inventory.purchase_receipt",
        "inventory.sales_invoice",
        "inventory.customer_return",
        "inventory.supplier_return",
        "inventory.purchase_order.create",
        "inventory.purchase_order.receive",
        "inventory.sales_order.create",
        "inventory.sales_order.ship",
        "inventory.sales_order.invoice",
    }
    if source.action not in taxable_actions:
        if source.action == "inventory.adjustment":
            item = values.get("item")
            unit = values.get("unit_cost")
            if (
                unit is None or services._q_qty(values.get("quantity_delta", 0)) < 0
            ) and item is not None:
                unit = services.get_average_unit_cost(item)
            if unit is None:
                return None
            unit = services._q_qty(unit)
            return abs(
                Decimal(str(values.get("quantity_delta", 0))) * Decimal(str(unit))
            ).quantize(Decimal(".01"), rounding=ROUND_HALF_UP)
        if source.action == "inventory.stock_count.post":
            count = values.get("stock_count")
            return sum(
                (
                    abs(line.variance_quantity)
                    * services.get_average_unit_cost(line.item)
                    for line in count.lines.select_related("item")
                ),
                Decimal("0"),
            ).quantize(Decimal(".01"), rounding=ROUND_HALF_UP)
        return _proposal_amount(source, payload)
    lines = values.get("lines")
    if not lines:
        if values.get("item") is not None:
            lines = [
                {
                    key: values[key]
                    for key in (
                        "item",
                        "quantity",
                        "unit_cost",
                        "unit_price",
                        "vat_rate",
                        "wht_rate",
                    )
                    if key in values
                }
            ]
        elif values.get("sales_order") is not None:
            lines = [
                {
                    "item": line.item,
                    "quantity": line.shipped_quantity
                    if line.shipped_quantity > 0
                    else line.quantity,
                    "unit_price": line.unit_price,
                    "vat_rate": line.vat_rate,
                    "wht_rate": 0,
                }
                for line in values["sales_order"].lines.all()
            ]
        else:
            return None
    transaction_type = (
        "PURCHASE"
        if source.action
        in {
            "inventory.purchase_receipt",
            "inventory.supplier_return",
            "inventory.purchase_order.create",
            "inventory.purchase_order.receive",
        }
        else "SALE"
    )
    total = Decimal("0")
    for line in lines:
        reference = line.get("purchase_order_line") or line.get("sales_order_line")
        item = line.get("item") or getattr(reference, "item", None)
        unit = line.get("unit_cost", line.get("unit_price"))
        if unit is None and reference is not None:
            unit = getattr(
                reference, "unit_cost", getattr(reference, "unit_price", None)
            )
        if (
            item is not None
            and source.action
            in {"inventory.sales_invoice", "inventory.customer_return"}
            and not unit
        ):
            unit = item.default_sales_price
        if item is None or unit is None:
            return None
        quantity = services._q_qty(line.get("quantity", 0))
        unit = services._q_qty(unit)
        taxes = services.calculate_inventory_line_taxes(
            company=source.company,
            item=item,
            quantity=quantity,
            unit_price=unit,
            transaction_type=transaction_type,
            tax_date=values.get("posting_date")
            or values.get("order_date")
            or timezone.now().date(),
        )
        if "vat_rate" in line:
            vat = services._rate(line["vat_rate"])
        elif source.action in {
            "inventory.purchase_order.create",
            "inventory.sales_order.create",
        }:
            vat = Decimal("0")
        elif reference is not None and (
            source.action == "inventory.sales_order.ship"
            or getattr(reference, "vat_rate", 0)
        ):
            vat = services._rate(reference.vat_rate)
        elif source.action in {
            "inventory.customer_return",
            "inventory.supplier_return",
        }:
            vat = services._rate(item.default_vat_rate)
        else:
            vat = taxes["vat_rate"]
        total += taxes["taxable_amount"] + services._rate_amount(
            taxes["taxable_amount"], vat
        )
    return total.quantize(Decimal(".01"), rounding=ROUND_HALF_UP)


def inventory_proposal_snapshot(source):
    atomic = transaction.get_connection().in_atomic_block
    if atomic:
        type(source.company)._base_manager.select_for_update().get(pk=source.company_id)
    result = proposal_snapshot(source)
    values = decode_value(source.parameters, source.company)
    item_ids = set()

    def collect(value):
        if isinstance(value, models.InventoryItem):
            item_ids.add(value.pk)
        elif isinstance(value, dict):
            for child in value.values():
                collect(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                collect(child)
        elif hasattr(value, "item_id"):
            item_ids.add(value.item_id)

    collect(values)
    for key in ("stock_count", "sales_order"):
        parent = values.get(key)
        if parent:
            item_ids.update(parent.lines.values_list("item_id", flat=True))
    if atomic:
        list(
            models.InventoryItem.objects.select_for_update()
            .filter(company=source.company, pk__in=item_ids)
            .order_by("pk")
        )
        list(
            models.InventoryValuationLayer.objects.select_for_update()
            .filter(company=source.company, item_id__in=item_ids)
            .order_by("pk")
        )
        list(
            models.StockMovement.objects.select_for_update()
            .filter(company=source.company, item_id__in=item_ids)
            .order_by("pk")
        )
        list(
            models.TaxJurisdiction.objects.select_for_update()
            .filter(company=source.company)
            .order_by("pk")
        )
        list(
            models.TaxRule.objects.select_for_update()
            .filter(company=source.company)
            .order_by("pk")
        )
    result["reviewed_gross_exposure"] = str(inventory_exposure(source, {}))
    result["tax_rules"] = list(
        models.TaxRule.objects.filter(company=source.company).order_by("pk").values()
    )
    result["tax_jurisdictions"] = list(
        models.TaxJurisdiction.objects.filter(company=source.company)
        .order_by("pk")
        .values()
    )
    return result


_OPERATIONS = {
    "post_opening_stock": "inventory.opening_stock",
    "post_purchase_receipt": "inventory.purchase_receipt",
    "post_sales_invoice": "inventory.sales_invoice",
    "post_customer_payment": "inventory.customer_payment",
    "post_supplier_payment": "inventory.supplier_payment",
    "post_tax_remittance": "inventory.tax_remittance",
    "post_customer_return": "inventory.customer_return",
    "post_supplier_return": "inventory.supplier_return",
    "post_inventory_adjustment": "inventory.adjustment",
    "post_stock_transfer": "inventory.transfer",
    "post_stock_count_adjustments": "inventory.stock_count.post",
    "post_vendor_bill": "inventory.vendor_bill.post",
    "post_landed_cost": "inventory.landed_cost.post",
    "post_stock_transfer_shipment": "inventory.transfer.dispatch",
    "receive_transfer_shipment": "inventory.transfer.receive",
    "create_purchase_order": "inventory.purchase_order.create",
    "receive_purchase_order": "inventory.purchase_order.receive",
    "create_sales_order": "inventory.sales_order.create",
    "ship_sales_order": "inventory.sales_order.ship",
    "repair_sales_order_invoice": "inventory.sales_order.invoice",
    "reverse_inventory_document": "inventory.document.reverse",
    "provision_bad_debt": "inventory.bad_debt.provision",
    "allocate_customer_payment": "inventory.customer_payment.allocate",
    "allocate_supplier_payment": "inventory.supplier_payment.allocate",
}
for name, key in _OPERATIONS.items():
    operation = getattr(services, name, None)
    if operation is not None:
        setattr(
            services,
            name,
            proposal_operation(
                key,
                "inventory.change_inventorydocument",
                submit_permission="inventory.add_inventorydocument",
                amount=inventory_exposure,
                snapshot=inventory_proposal_snapshot,
            )(operation),
        )


def _snapshot(source):
    data = {
        f.attname: getattr(source, f.attname)
        for f in source._meta.concrete_fields
        if f.name
        not in {"created_at", "updated_at", "approved_at", "approved_by", "status"}
    }
    if hasattr(source, "lines"):
        data["lines"] = list(source.lines.order_by("pk").values())
    return data


def _validate(source, payload):
    if source.status not in {"DRAFT", "PENDING_APPROVAL", "COUNTED"}:
        raise ValidationError("Only an unapproved document can enter approval.")
    if isinstance(source, models.StockCount) and not source.lines.exists():
        raise ValidationError("A stock count needs count lines before approval.")


def _approve(source, actor, payload):
    source.status = source.Status.APPROVED
    source.approved_by = actor
    source.approved_at = timezone.now()
    source.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])


def _reject_document(source, actor, payload):
    source.status = models.InventoryDocument.Status.CANCELLED
    source.save(update_fields=["status", "updated_at"])


for model, key in [
    (models.InventoryDocument, "inventory.document.approve"),
    (models.StockCount, "inventory.stock_count.approve"),
]:
    register_action(
        ApprovalAction(
            key=key,
            model_label=model._meta.label,
            permission="inventory.change_inventorydocument",
            apply=_approve,
            snapshot=_snapshot,
            validate=_validate,
            requester=lambda source: getattr(source, "requested_by", None),
            amount=lambda source, payload: getattr(source, "total_amount", None),
            reject=_reject_document if model is models.InventoryDocument else None,
        )
    )


def approve_inventory_document(source, user=None):
    from approvals.proposals import _request_actor
    from approvals.models import ApprovalRequest
    from django.contrib.contenttypes.models import ContentType

    actor = user or _request_actor.get()
    key = (
        "inventory.stock_count.approve"
        if isinstance(source, models.StockCount)
        else "inventory.document.approve"
    )
    if current_execution():
        return _approve(source, actor, {})
    ct = ContentType.objects.get_for_model(source)
    pending = ApprovalRequest.objects.filter(
        content_type=ct, object_id=source.pk, action=key, status="PENDING"
    ).first()
    if pending or getattr(source, "requested_by_id", None):
        return request_or_decide(source=source, action=key, actor=actor)
    require_company_authority(
        actor, source.company, "inventory.change_inventorydocument"
    )
    return submit_approval(source=source, action=key, requester=actor)


services.approve_inventory_document = approve_inventory_document


def validate_variance(source, payload):
    if source.investigation_status != "PENDING" or source.stock_count.status not in {
        "DRAFT",
        "COUNTED",
    }:
        raise ValidationError(
            "Only a pending variance on an unapproved count may be reviewed."
        )


def reject_variance(source, actor, payload):
    source.investigation_status = "REJECTED"
    source.save(update_fields=["investigation_status", "updated_at"])


def approve_variance(source, actor, payload):
    source.investigation_status = "APPROVED"
    source.save(update_fields=["investigation_status", "updated_at"])


register_action(
    ApprovalAction(
        key="inventory.stock_variance.approve",
        model_label="inventory.StockCountLine",
        permission="inventory.change_stockcount",
        apply=approve_variance,
        snapshot=_snapshot,
        validate=validate_variance,
        reject=reject_variance,
        company=lambda source: source.stock_count.company,
    )
)


# Allocations are durable financial history, including parent cascades.
from django.db.models.signals import pre_delete


def protect_allocation(sender, instance, **kwargs):
    raise ValidationError(
        "Payment allocation history cannot be deleted, including through its payment."
    )


for allocation_model in (
    models.CustomerPaymentAllocation,
    models.SupplierPaymentAllocation,
):
    pre_delete.connect(
        protect_allocation,
        sender=allocation_model,
        weak=False,
        dispatch_uid="approval-allocation-" + allocation_model._meta.label_lower,
    )


for child_label in models.FINANCIAL_CHILD_MODELS:
    from django.apps import apps

    pre_delete.connect(
        protect_allocation,
        sender=apps.get_model(child_label),
        weak=False,
        dispatch_uid="approval-financial-child-" + child_label,
    )
