"""Inventory fixtures always exercise real independent workflow decisions."""
from functools import wraps
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.apps import apps
from approvals.models import ApprovalRequest
from approvals.registry import get_action
from tests.approval_helpers import approved_operation, approve_request
from approvals.proposals import object_company


def inventory_actor(company, *, checker=False):
    role = "checker" if checker else "maker"
    user, _ = get_user_model().objects.get_or_create(
        email=f"inventory-{role}-{company.pk}@fixtures.test",
        defaults={"company": company, "active_company": company, "is_active": True},
    )
    codes = (
        ["change_inventorydocument", "change_stockcount"]
        if checker
        else ["add_inventorydocument", "change_inventorydocument"]
    )
    user.user_permissions.add(
        *Permission.objects.filter(
            content_type__app_label="inventory", codename__in=codes
        )
    )
    return user


def resolve_approval(approval):
    return approve_request(approval)


def approved_inventory_operation(operation):
    @wraps(operation)
    def call(*args, **kwargs):
        company = kwargs.get("company")
        if company is None:
            for value in [*args, *kwargs.values()]:
                if hasattr(value, "_meta"):
                    company = object_company(value)
                    if company:
                        break
        return approved_operation(
            operation,
            *args,
            maker=inventory_actor(company),
            permission="inventory.change_inventorydocument",
            **kwargs,
        )

    return call


def approve_inventory_source(source):
    from inventory.services import approve_inventory_document

    approval = approve_inventory_document(source, user=inventory_actor(source.company))
    return resolve_approval(approval)


def finish_web_approval(test, response):
    if response.status_code == 302 and response.url.startswith("/approvals/"):
        approval = ApprovalRequest.objects.get(
            pk=int(response.url.strip("/").split("/")[-1])
        )
        test.assertEqual(approval.status, "PENDING")
        return resolve_approval(approval)


def finish_api_approval(test, response):
    test.assertEqual(response.status_code, 202, response.data)
    test.assertEqual(response.data["status"], "PENDING")
    approval = ApprovalRequest.objects.get(pk=response.data["approval_id"])
    return resolve_approval(approval)


def historical_sales_order(**fields):
    """Seed pre-workflow history using Django migration-state models.

    Live guards remain enabled. Foreign keys use IDs because historical models
    are isolated from runtime model classes, as in a real migration.
    """
    from django.db.migrations.state import StateApps, ModelState
    from inventory.models import SalesOrder

    model_states = {
        (model._meta.app_label, model._meta.model_name): ModelState.from_model(model)
        for model in apps.get_models()
    }
    historical_apps = StateApps(set(), model_states)
    old_order = historical_apps.get_model("inventory", "SalesOrder").objects.create(
        **fields
    )
    return SalesOrder.objects.get(pk=old_order.pk)


def historical_sales_order_line(**fields):
    """Seed detail rows of pre-workflow order history without runtime guard bypasses."""
    from django.db.migrations.state import StateApps, ModelState
    from inventory.models import SalesOrderLine
    model_states = {
        (model._meta.app_label, model._meta.model_name): ModelState.from_model(model)
        for model in apps.get_models()
    }
    historical_apps = StateApps(set(), model_states)
    old_line = historical_apps.get_model('inventory', 'SalesOrderLine').objects.create(**fields)
    return SalesOrderLine.objects.get(pk=old_line.pk)
