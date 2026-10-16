from collections.abc import Mapping
from django.apps import apps
from django.core.exceptions import (
    ValidationError as DjangoValidationError,
    PermissionDenied,
)
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from .access import visible_requests, selected_company
from .permissions import has_company_permission, can_decide
from .presentation import request_context, action_label
from .registry import get_action
from .services import submit_approval, decide_approval, cancel_approval, _company


def representation(approval, user):
    context = request_context(approval, user=user)
    return {
        "id": approval.pk,
        "action": approval.action,
        "label": context["action_label"],
        "source": context["source_label"],
        "source_id": approval.object_id,
        "status": approval.status,
        "requester": str(approval.requester),
        "created_at": approval.created_at,
        "current_stage": approval.current_stage + 1,
        "can_decide": can_decide(approval, user),
        "can_cancel": approval.status == "PENDING" and approval.requester_id == user.pk,
        "fields": [
            {"label": label, "value": value}
            for label, value in context["business_fields"]
        ],
        "stages": approval.policy_snapshot.get("stages", []),
        "timeline": [
            {
                "kind": event.kind,
                "actor": str(event.actor),
                "at": event.created_at,
                "detail": event.detail if context["can_view_business_content"] else {},
            }
            for event in approval.events.select_related("actor").all()
        ],
    }


class Inbox(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        rows = visible_requests(request.user)
        status = request.query_params.get("status")
        if status:
            rows = rows.filter(status=status)
        paginator = PageNumberPagination()
        paginator.page_size = 25
        page = paginator.paginate_queryset(rows, request)
        return paginator.get_paginated_response(
            [representation(row, request.user) for row in page]
        )


class Detail(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        return Response(
            representation(
                get_object_or_404(visible_requests(request.user), pk=pk), request.user
            )
        )


class Decide(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        if not isinstance(request.data, Mapping):
            return Response({"detail": "Request body must be an object."}, status=400)
        approval = get_object_or_404(visible_requests(request.user), pk=pk)
        decision = request.data.get("decision", "APPROVE")
        comment = request.data.get("comment", "")
        if not isinstance(comment, str):
            return Response({"detail": "Comment must be text."}, status=400)
        try:
            approval = decide_approval(
                approval=approval,
                actor=request.user,
                decision=decision,
                comment=comment,
            )
        except DjangoValidationError as exc:
            return Response({"detail": exc.messages}, status=400)
        return Response(representation(approval, request.user))


class Cancel(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        if not isinstance(request.data, Mapping):
            return Response({"detail": "Request body must be an object."}, status=400)
        approval = get_object_or_404(visible_requests(request.user), pk=pk)
        reason = request.data.get("reason", "")
        if not isinstance(reason, str):
            return Response({"detail": "Reason must be text."}, status=400)
        try:
            approval = cancel_approval(
                approval=approval, actor=request.user, reason=reason
            )
        except DjangoValidationError as exc:
            return Response({"detail": exc.messages}, status=400)
        return Response(representation(approval, request.user))


class Submit(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not isinstance(request.data, Mapping):
            return Response({"detail": "Request body must be an object."}, status=400)
        try:
            key = request.data.get("action")
            if not isinstance(key, str):
                raise DjangoValidationError("An approval action is required.")
            adapter = get_action(key)
            source_id = request.data.get("source_id")
            if type(source_id) is not int or source_id < 1:
                raise DjangoValidationError("Source ID must be a positive integer.")
            model = apps.get_model(adapter.model_label)
            source = get_object_or_404(model._base_manager, pk=source_id)
            company = selected_company(request.user)
            if _company(source, adapter).pk != company.pk:
                raise PermissionDenied("Source belongs to a different company.")
            maker = adapter.requester(source) if adapter.requester else None
            if maker is not None and maker.pk != request.user.pk:
                raise PermissionDenied(
                    "Only the original maker may submit this source."
                )
            if maker is None and not has_company_permission(
                request.user, company, adapter.permission
            ):
                raise PermissionDenied(
                    "Action authority is required to submit a source with no known maker."
                )
            approval = submit_approval(
                source=source,
                action=key,
                requester=request.user,
                payload=request.data.get("payload"),
            )
        except DjangoValidationError as exc:
            return Response({"detail": exc.messages}, status=400)
        return Response(representation(approval, request.user), status=201)
