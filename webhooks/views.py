"""Change-feed views (P1-9): BambooHR "Get Changed Employees" analogue.

``GET /webhooks/changed-employees/?since=<ISO-8601>`` returns the employee
records for the caller's company whose ``updated_at`` is strictly after
``since``. Callers poll with the latest timestamp they have seen to fetch a
delta rather than the full roster.
"""
from __future__ import annotations

from datetime import datetime

from django.http import JsonResponse
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_GET

from company.utils import get_user_company
from payroll.models import EmployeeProfile


@require_GET
def changed_employees(request):
    """Return employees for the caller's company created after ``since``.

    ``EmployeeProfile`` is a ``SoftDeleteModel`` and has no ``updated_at``
    (it tracks a ``created`` ctime only), so this delta feed reports new
    employees. Soft-deleted rows are excluded via the default manager.
    """
    company = get_user_company(request.user)
    if company is None:
        return JsonResponse({"detail": "No active company."}, status=400)

    since_raw = request.GET.get("since")
    if not since_raw:
        return JsonResponse(
            {"detail": "Query parameter 'since' is required."}, status=400
        )
    since = parse_datetime(since_raw)
    if since is None:
        try:
            since = datetime.fromisoformat(since_raw)
        except ValueError:
            return JsonResponse(
                {"detail": "'since' must be an ISO-8601 timestamp."},
                status=400,
            )

    changed = (
        EmployeeProfile.objects.filter(company=company, created__gt=since)
        .order_by("created")
        .values("id", "first_name", "last_name", "email", "status", "created")
    )
    employees = [
        {**row, "created": row["created"].isoformat()} for row in changed
    ]
    return JsonResponse(
        {
            "count": len(employees),
            "since": since.isoformat(),
            "employees": employees,
        }
    )
