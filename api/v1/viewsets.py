from __future__ import annotations

from datetime import date
from zoneinfo import ZoneInfo

from django.db import models, transaction
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_date
from django.utils import timezone
from django.utils.text import slugify
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import DjangoModelPermissions, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers as drf_serializers

from accounting.models import Account, AccountingPeriod, FiscalYear, Journal, JournalEntry
from company.models import Company
from company.utils import get_user_companies, get_user_company, set_active_company
from payroll.models import (
    CompanyChatMessage,
    CompanyChatReadState,
    CompanyChatRoom,
    CompanyChatRoomMember,
    Department,
    EmployeeProfile,
    IOU,
    LeavePolicy,
    LeaveRequest,
    Payroll,
    PayrollEntry,
    PayrollRun,
    PayrollRunEntry,
)
from standup.models import (
    StandupAnswer,
    StandupCheckin,
    StandupFollow,
    StandupQuestion,
    StandupTeam,
    StandupTeamMember,
)

from api.v1.permissions import CanMutateAccounting, IsAccountingRole, IsTenantMember
from api.v1.serializers import (
    AccountSerializer,
    AccountingPeriodSerializer,
    CompanyChatRoomCreateSerializer,
    CompanyChatRoomMemberSerializer,
    CompanyChatRoomSerializer,
    CompanyChatMessageCreateSerializer,
    CompanyChatMessageSerializer,
    CompanyChatSenderSerializer,
    CompanyMembershipSerializer,
    DepartmentSerializer,
    EmployeeProfileSerializer,
    FiscalYearSerializer,
    IOUSerializer,
    JournalEntrySerializer,
    JournalSerializer,
    LeavePolicySerializer,
    LeaveRequestSerializer,
    PayrollEntrySerializer,
    PayrollRunEntrySerializer,
    PayrollRunSerializer,
    PayrollSerializer,
    StandupCheckinSerializer,
    StandupFollowSerializer,
    StandupQuestionSerializer,
    StandupTeamMemberSerializer,
    StandupTeamSerializer,
)
from payroll.services.chat_service import (
    broadcast_company_chat_message,
    create_company_chat_message,
    create_room_message,
    get_company_chat_room,
    get_or_create_direct_room,
    is_room_member,
    mark_company_chat_read,
)


class TenantScopedModelViewSet(viewsets.ModelViewSet):
    """
    Generic company-scoped viewset.
    Set `company_filter_path` when company is accessible via relation.
    """

    permission_classes = [IsAuthenticated, IsTenantMember, DjangoModelPermissions]
    company_filter_path = "company"

    def get_company(self):
        return get_user_company(self.request.user)

    def get_queryset(self):
        queryset = super().get_queryset()
        company = self.get_company()
        if company is None:
            return queryset.none()
        if self.request.user.is_superuser:
            return queryset
        return queryset.filter(**{self.company_filter_path: company})

    def perform_create(self, serializer):
        company = self.get_company()
        if company is None:
            serializer.save()
            return

        field_name = self.company_filter_path.split("__")[0]
        model_fields = {field.name for field in serializer.Meta.model._meta.get_fields()}
        if field_name in model_fields:
            serializer.save(**{field_name: company})
        else:
            serializer.save()


class SuperuserOnlyAccountingMixin:
    """
    Temporary safety gate for accounting APIs until models are fully tenant-scoped.
    """

    def _ensure_superuser(self):
        if not self.request.user.is_superuser:
            raise PermissionDenied(
                "Accounting API access is temporarily restricted to superusers."
            )


class DepartmentViewSet(TenantScopedModelViewSet):
    queryset = Department.objects.all().order_by("name")
    serializer_class = DepartmentSerializer
    search_fields = ["name"]
    ordering_fields = ["name"]


class EmployeeViewSet(TenantScopedModelViewSet):
    queryset = (
        EmployeeProfile.objects.select_related("department", "user", "company")
        .all()
        .order_by("-created")
    )
    serializer_class = EmployeeProfileSerializer
    search_fields = ["first_name", "last_name", "email", "emp_id"]
    ordering_fields = ["created", "first_name", "last_name"]

    @action(detail=False, methods=["get"], permission_classes=[IsAuthenticated, IsTenantMember])
    def me(self, request):
        employee = get_object_or_404(self.get_queryset(), user=request.user)
        serializer = self.get_serializer(employee)
        return Response(serializer.data)


class CompanyChatMessageViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated, IsTenantMember]

    def get_company(self):
        return get_user_company(self.request.user)

    def get_room(self):
        company = self.get_company()
        if company is None:
            raise PermissionDenied("No active company is configured for this account.")
        return get_company_chat_room(company)

    def get_queryset(self):
        company = self.get_company()
        if company is None:
            return CompanyChatMessage.objects.none()
        room_id = self.request.query_params.get("room_id")
        if room_id:
            room = get_object_or_404(CompanyChatRoom, id=room_id, company=company)
            employee = getattr(self.request.user, "employee_user", None)
            if room.room_type != CompanyChatRoom.TYPE_COMPANY and not is_room_member(room, employee):
                return CompanyChatMessage.objects.none()
        else:
            room = get_company_chat_room(company)
        return (
            CompanyChatMessage.objects.select_related("room", "sender", "sender__user")
            .filter(room=room)
            .order_by("created_at", "id")
        )

    def get_serializer_class(self):
        if self.action == "create":
            return CompanyChatMessageCreateSerializer
        return CompanyChatMessageSerializer

    def _get_employee(self):
        employee = getattr(self.request.user, "employee_user", None)
        company = self.get_company()
        if employee is None:
            raise PermissionDenied("This account is not linked to an employee profile.")
        if company is None or employee.company_id != company.id:
            raise PermissionDenied("Employee profile is not attached to the active company.")
        return employee

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        employee = self._get_employee()
        room_id = serializer.validated_data.get("room_id") or request.data.get("room_id")
        if room_id:
            room = get_object_or_404(CompanyChatRoom, id=room_id, company=employee.company)
            if not is_room_member(room, employee):
                raise PermissionDenied("You are not a member of this room.")
            message = create_room_message(room, employee, serializer.validated_data["body"])
        else:
            message = create_company_chat_message(
                employee,
                serializer.validated_data["body"],
            )
        broadcast_company_chat_message(message)

        output = CompanyChatMessageSerializer(
            message,
            context=self.get_serializer_context(),
        )
        headers = self.get_success_headers(output.data)
        return Response(output.data, status=status.HTTP_201_CREATED, headers=headers)

    @action(detail=False, methods=["post"], url_path="mark-read")
    def mark_read(self, request):
        class MarkReadSerializer(drf_serializers.Serializer):
            message_id = drf_serializers.IntegerField(required=False)
            room_id = drf_serializers.IntegerField(required=False)

        serializer = MarkReadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        employee = self._get_employee()
        room_id = serializer.validated_data.get("room_id")
        if room_id:
            room = get_object_or_404(CompanyChatRoom, id=room_id, company=employee.company)
            if not is_room_member(room, employee):
                raise PermissionDenied("You are not a member of this room.")
        else:
            room = self.get_room()
        message = None
        message_id = serializer.validated_data.get("message_id")
        if message_id is not None:
            message = get_object_or_404(self.get_queryset(), pk=message_id)

        state = mark_company_chat_read(room, employee, message)
        return Response(
            {
                "room": room.id,
                "last_read_message_id": state.last_read_message_id,
                "last_read_at": state.last_read_at,
            }
        )


class CompanyChatRoomViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated, IsTenantMember]

    def get_company(self):
        return get_user_company(self.request.user)

    def get_queryset(self):
        company = self.get_company()
        if company is None:
            return CompanyChatRoom.objects.none()
        employee = getattr(self.request.user, "employee_user", None)
        if employee is None:
            return CompanyChatRoom.objects.none()
        member_room_ids = CompanyChatRoomMember.objects.filter(
            employee=employee,
            is_active=True,
        ).values_list("room_id", flat=True)
        return CompanyChatRoom.objects.filter(
            company=company,
            is_active=True,
        ).filter(
            models.Q(room_type=CompanyChatRoom.TYPE_COMPANY) | models.Q(id__in=member_room_ids)
        )

    def get_serializer_class(self):
        if self.action == "create":
            return CompanyChatRoomCreateSerializer
        return CompanyChatRoomSerializer

    def _get_employee(self):
        employee = getattr(self.request.user, "employee_user", None)
        company = self.get_company()
        if employee is None:
            raise PermissionDenied("This account is not linked to an employee profile.")
        if company is None or employee.company_id != company.id:
            raise PermissionDenied("Employee profile is not attached to the active company.")
        return employee

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        employee = self._get_employee()
        payload = serializer.validated_data
        slug = payload.get("slug") or None

        room = CompanyChatRoom.objects.create(
            company=employee.company,
            slug=slugify(slug or payload["name"]),
            name=payload["name"],
            description=payload.get("description", ""),
            room_type=payload["room_type"],
            created_by=employee,
        )
        CompanyChatRoomMember.objects.create(room=room, employee=employee, role="admin")

        output = CompanyChatRoomSerializer(room, context=self.get_serializer_context())
        return Response(output.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"], url_path="direct")
    def direct(self, request):
        class DirectRoomSerializer(drf_serializers.Serializer):
            employee_id = drf_serializers.IntegerField()

        serializer = DirectRoomSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        employee = self._get_employee()
        target_employee = get_object_or_404(
            EmployeeProfile,
            id=serializer.validated_data["employee_id"],
            company=employee.company,
        )
        room, created = get_or_create_direct_room(employee.company, employee, target_employee)
        output = CompanyChatRoomSerializer(room, context=self.get_serializer_context())
        return Response(output.data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    @action(detail=True, methods=["get"], url_path="members")
    def members(self, request, pk=None):
        room = get_object_or_404(self.get_queryset(), pk=pk)
        employee = self._get_employee()
        if not is_room_member(room, employee):
            raise PermissionDenied("You are not a member of this room.")

        memberships = CompanyChatRoomMember.objects.filter(room=room, is_active=True).select_related(
            "employee", "employee__user"
        )
        serializer = CompanyChatRoomMemberSerializer(memberships, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="candidates")
    def candidates(self, request):
        employee = self._get_employee()
        search = (request.query_params.get("search") or "").strip()
        queryset = EmployeeProfile.objects.filter(company=employee.company)
        if search:
            queryset = queryset.filter(
                models.Q(first_name__icontains=search)
                | models.Q(last_name__icontains=search)
                | models.Q(email__icontains=search)
                | models.Q(user__email__icontains=search)
            )
        queryset = queryset.select_related("user").order_by("first_name", "last_name")[:20]
        serializer = CompanyChatSenderSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="add-member")
    def add_member(self, request, pk=None):
        room = get_object_or_404(CompanyChatRoom, pk=pk, company=self.get_company())
        employee = self._get_employee()
        membership = CompanyChatRoomMember.objects.filter(
            room=room,
            employee=employee,
            is_active=True,
        ).first()
        if not membership or membership.role != CompanyChatRoomMember.ROLE_ADMIN:
            raise PermissionDenied("Only room admins can add members.")

        class AddMemberSerializer(drf_serializers.Serializer):
            employee_id = drf_serializers.IntegerField()

        serializer = AddMemberSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        target_employee = get_object_or_404(
            EmployeeProfile,
            id=serializer.validated_data["employee_id"],
            company=employee.company,
        )
        new_member, _ = CompanyChatRoomMember.objects.get_or_create(
            room=room,
            employee=target_employee,
            defaults={"role": CompanyChatRoomMember.ROLE_MEMBER},
        )
        output = CompanyChatRoomMemberSerializer(new_member)
        return Response(output.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"], url_path="unread")
    def unread(self, request):
        employee = self._get_employee()
        member_room_ids = CompanyChatRoomMember.objects.filter(
            employee=employee,
            is_active=True,
        ).values_list("room_id", flat=True)
        rooms = list(
            CompanyChatRoom.objects.filter(
                company=employee.company,
                is_active=True,
            ).filter(
                models.Q(room_type=CompanyChatRoom.TYPE_COMPANY)
                | models.Q(id__in=member_room_ids)
            )
        )
        if not rooms:
            rooms = [get_company_chat_room(employee.company)]

        room_ids = [room.id for room in rooms]
        read_states = {
            state.room_id: state
            for state in CompanyChatReadState.objects.filter(
                room_id__in=room_ids,
                employee=employee,
            )
        }

        room_counts = []
        total_unread = 0
        for room in rooms:
            state = read_states.get(room.id)
            if state and state.last_read_at:
                unread_count = CompanyChatMessage.objects.filter(
                    room=room,
                    created_at__gt=state.last_read_at,
                ).count()
            else:
                unread_count = CompanyChatMessage.objects.filter(room=room).count()
            total_unread += unread_count
            room_counts.append(
                {
                    "room_id": room.id,
                    "unread_count": unread_count,
                }
            )

        return Response({"total_unread": total_unread, "rooms": room_counts})


class PayrollViewSet(TenantScopedModelViewSet):
    queryset = Payroll.objects.all().order_by("-timestamp")
    serializer_class = PayrollSerializer
    search_fields = ["status"]
    ordering_fields = ["timestamp", "updated", "basic_salary"]


class PayrollEntryViewSet(TenantScopedModelViewSet):
    queryset = PayrollEntry.objects.select_related("pays", "company").all().order_by("-id")
    serializer_class = PayrollEntrySerializer
    search_fields = ["pays__first_name", "pays__last_name", "status"]
    ordering_fields = ["id", "netpay"]


class PayrollRunViewSet(TenantScopedModelViewSet):
    queryset = PayrollRun.objects.all().order_by("-paydays")
    serializer_class = PayrollRunSerializer
    search_fields = ["name", "slug"]
    ordering_fields = ["paydays", "name"]

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        payroll_run = self.get_object()
        if payroll_run.closed:
            return Response(
                {"detail": "Payroll run is already closed."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        payroll_run.closed = True
        payroll_run.save(update_fields=["closed"])
        return Response({"detail": "Payroll run closed successfully."})


class PayrollRunEntryViewSet(TenantScopedModelViewSet):
    queryset = (
        PayrollRunEntry.objects.select_related("payroll_run", "payroll_entry", "payroll_entry__company")
        .all()
        .order_by("-id")
    )
    serializer_class = PayrollRunEntrySerializer
    company_filter_path = "payroll_entry__company"
    ordering_fields = ["id", "payroll_run"]


class LeavePolicyViewSet(TenantScopedModelViewSet):
    queryset = LeavePolicy.objects.all().order_by("leave_type")
    serializer_class = LeavePolicySerializer
    ordering_fields = ["leave_type", "max_days"]


class LeaveRequestViewSet(TenantScopedModelViewSet):
    queryset = LeaveRequest.objects.select_related("employee", "approved_by").all().order_by("-created_at")
    serializer_class = LeaveRequestSerializer
    company_filter_path = "employee__company"
    search_fields = ["employee__first_name", "employee__last_name", "leave_type", "status"]
    ordering_fields = ["created_at", "start_date", "end_date", "status"]

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        leave_request = self.get_object()
        leave_request.status = "APPROVED"
        leave_request.approved_by = request.user
        leave_request.save(user=request.user)
        return Response({"detail": "Leave request approved."})

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        leave_request = self.get_object()
        leave_request.status = "REJECTED"
        leave_request.approved_by = request.user
        leave_request.save(user=request.user)
        return Response({"detail": "Leave request rejected."})


class IOUViewSet(TenantScopedModelViewSet):
    queryset = IOU.objects.select_related("employee_id").all().order_by("-created_at")
    serializer_class = IOUSerializer
    company_filter_path = "employee_id__company"
    search_fields = ["employee_id__first_name", "employee_id__last_name", "status"]
    ordering_fields = ["created_at", "amount", "status", "due_date"]

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        iou = self.get_object()
        iou.status = "APPROVED"
        iou.approved_at = timezone.now().date()
        iou.save()
        return Response({"detail": "IOU approved."})

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        iou = self.get_object()
        iou.status = "REJECTED"
        iou.save()
        return Response({"detail": "IOU rejected."})

    @action(detail=True, methods=["post"])
    def mark_paid(self, request, pk=None):
        iou = self.get_object()
        iou.status = "PAID"
        iou.save()
        return Response({"detail": "IOU marked as paid."})


class AccountViewSet(SuperuserOnlyAccountingMixin, TenantScopedModelViewSet):
    queryset = Account.objects.all().order_by("account_number", "name")
    serializer_class = AccountSerializer
    permission_classes = [IsAuthenticated, IsAccountingRole, CanMutateAccounting]
    company_filter_path = ""
    search_fields = ["name", "account_number", "type"]
    ordering_fields = ["account_number", "name", "created_at"]

    def get_queryset(self):
        self._ensure_superuser()
        return self.queryset


class FiscalYearViewSet(SuperuserOnlyAccountingMixin, TenantScopedModelViewSet):
    queryset = FiscalYear.objects.all().order_by("-year")
    serializer_class = FiscalYearSerializer
    permission_classes = [IsAuthenticated, IsAccountingRole, CanMutateAccounting]
    company_filter_path = ""
    search_fields = ["year", "name"]
    ordering_fields = ["year", "start_date", "end_date"]

    def get_queryset(self):
        self._ensure_superuser()
        return self.queryset

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        self._ensure_superuser()
        fiscal_year = self.get_object()
        fiscal_year.close(request.user)
        return Response({"detail": "Fiscal year closed."})


class AccountingPeriodViewSet(SuperuserOnlyAccountingMixin, TenantScopedModelViewSet):
    queryset = AccountingPeriod.objects.select_related("fiscal_year").all().order_by("-fiscal_year__year", "-period_number")
    serializer_class = AccountingPeriodSerializer
    permission_classes = [IsAuthenticated, IsAccountingRole, CanMutateAccounting]
    company_filter_path = ""
    search_fields = ["name", "fiscal_year__name"]
    ordering_fields = ["period_number", "start_date", "end_date"]

    def get_queryset(self):
        self._ensure_superuser()
        return self.queryset

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        self._ensure_superuser()
        period = self.get_object()
        period.close(request.user)
        return Response({"detail": "Accounting period closed."})


class JournalViewSet(SuperuserOnlyAccountingMixin, TenantScopedModelViewSet):
    queryset = Journal.objects.select_related("period", "created_by", "approved_by", "posted_by").prefetch_related("entries").all().order_by("-created_at")
    serializer_class = JournalSerializer
    permission_classes = [IsAuthenticated, IsAccountingRole, CanMutateAccounting]
    company_filter_path = ""
    search_fields = ["transaction_number", "description", "status"]
    ordering_fields = ["created_at", "date", "status"]

    def get_queryset(self):
        self._ensure_superuser()
        return self.queryset

    def perform_create(self, serializer):
        self._ensure_superuser()
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        self._ensure_superuser()
        journal = self.get_object()
        journal.submit_for_approval()
        return Response({"detail": "Journal submitted for approval."})

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        self._ensure_superuser()
        journal = self.get_object()
        journal.approve(request.user)
        return Response({"detail": "Journal approved."})

    @action(detail=True, methods=["post"])
    def post(self, request, pk=None):
        self._ensure_superuser()
        journal = self.get_object()
        journal.post(request.user)
        return Response({"detail": "Journal posted."})

    @action(detail=True, methods=["post"])
    def reverse(self, request, pk=None):
        self._ensure_superuser()
        journal = self.get_object()
        reason = request.data.get("reason", "").strip() or "API reversal"
        reversal = journal.reverse(request.user, reason)
        data = self.get_serializer(reversal).data
        return Response(data, status=status.HTTP_201_CREATED)


class JournalEntryViewSet(SuperuserOnlyAccountingMixin, TenantScopedModelViewSet):
    queryset = JournalEntry.objects.select_related("journal", "account", "created_by").all().order_by("-created_at")
    serializer_class = JournalEntrySerializer
    permission_classes = [IsAuthenticated, IsAccountingRole, CanMutateAccounting]
    company_filter_path = ""
    search_fields = ["journal__transaction_number", "account__name", "entry_type"]
    ordering_fields = ["created_at", "amount"]

    def get_queryset(self):
        self._ensure_superuser()
        return self.queryset

    def perform_create(self, serializer):
        self._ensure_superuser()
        serializer.save(created_by=self.request.user)


class StandupTeamViewSet(TenantScopedModelViewSet):
    queryset = StandupTeam.objects.select_related("company").all().order_by("name")
    serializer_class = StandupTeamSerializer
    search_fields = ["name", "slug"]
    ordering_fields = ["name", "created_at", "updated_at"]

    @action(detail=True, methods=["get"], url_path="daily-summary")
    def daily_summary(self, request, pk=None):
        team = self.get_object()
        raw_work_date = request.query_params.get("work_date")
        if raw_work_date:
            work_date = parse_date(raw_work_date)
            if work_date is None:
                return Response(
                    {"detail": "work_date must be a valid ISO date (YYYY-MM-DD)."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            work_date = timezone.now().astimezone(ZoneInfo(team.timezone_name)).date()

        active_members = StandupTeamMember.objects.filter(team=team, is_active=True).select_related(
            "employee"
        )
        member_count = active_members.count()
        member_map = {membership.employee_id: membership.employee for membership in active_members}

        checkins = (
            StandupCheckin.objects.filter(team=team, work_date=work_date)
            .select_related("member")
            .prefetch_related("answers", "answers__question")
        )
        submitted_checkins = checkins.filter(status=StandupCheckin.STATUS_SUBMITTED)
        submitted_count = submitted_checkins.count()
        missed_count = checkins.filter(status=StandupCheckin.STATUS_MISSED).count()
        pending_count = max(member_count - submitted_count - missed_count, 0)

        blockers = []
        for checkin in submitted_checkins:
            for answer in checkin.answers.all():
                if not answer.is_blocker:
                    continue
                blockers.append(
                    {
                        "member_id": checkin.member_id,
                        "member_name": str(checkin.member),
                        "question": answer.question.prompt,
                        "body": answer.body,
                    }
                )

        members = []
        checkin_by_member = {checkin.member_id: checkin for checkin in checkins}
        for employee_id, employee in member_map.items():
            checkin = checkin_by_member.get(employee_id)
            members.append(
                {
                    "employee_id": employee_id,
                    "employee_name": str(employee),
                    "status": checkin.status if checkin else StandupCheckin.STATUS_DRAFT,
                    "submitted_at": checkin.submitted_at if checkin else None,
                    "blocker_count": checkin.blocker_count if checkin else 0,
                }
            )

        completion_rate = round((submitted_count / member_count) * 100, 2) if member_count else 0.0
        return Response(
            {
                "team": {"id": team.id, "name": team.name, "slug": team.slug},
                "work_date": work_date.isoformat(),
                "summary": {
                    "members": member_count,
                    "submitted": submitted_count,
                    "missed": missed_count,
                    "pending": pending_count,
                    "blockers": len(blockers),
                    "completion_rate": completion_rate,
                },
                "blockers": blockers,
                "members": members,
            }
        )


class StandupTeamMemberViewSet(TenantScopedModelViewSet):
    queryset = (
        StandupTeamMember.objects.select_related("team", "team__company", "employee", "employee__user")
        .all()
        .order_by("team__name", "employee__first_name")
    )
    serializer_class = StandupTeamMemberSerializer
    company_filter_path = "team__company"
    search_fields = ["team__name", "employee__first_name", "employee__last_name"]
    ordering_fields = ["joined_at", "team", "role"]


class StandupQuestionViewSet(TenantScopedModelViewSet):
    queryset = StandupQuestion.objects.select_related("team", "team__company").all().order_by("team", "order")
    serializer_class = StandupQuestionSerializer
    company_filter_path = "team__company"
    search_fields = ["team__name", "prompt"]
    ordering_fields = ["order", "created_at"]


class StandupCheckinViewSet(TenantScopedModelViewSet):
    queryset = (
        StandupCheckin.objects.select_related(
            "company", "team", "member", "member__user", "created_by"
        )
        .prefetch_related("answers", "answers__question")
        .all()
        .order_by("-work_date", "-updated_at")
    )
    serializer_class = StandupCheckinSerializer
    search_fields = ["team__name", "member__first_name", "member__last_name", "status"]
    ordering_fields = ["work_date", "created_at", "submitted_at", "status"]

    def perform_create(self, serializer):
        company = self.get_company()
        employee = get_object_or_404(
            EmployeeProfile,
            user=self.request.user,
            company=company,
        )
        serializer.save(
            company=company,
            member=employee,
            created_by=self.request.user,
        )

    @action(detail=False, methods=["post"])
    @transaction.atomic
    def submit(self, request):
        """
        Submit a standup check-in with answers.

        Payload:
        {
          "team": 1,
          "work_date": "2026-02-27",
          "answers": [{"question": 1, "body": "...", "is_blocker": false}]
        }
        """
        company = self.get_company()
        employee = get_object_or_404(
            EmployeeProfile,
            user=request.user,
            company=company,
        )
        team_id = request.data.get("team")
        raw_work_date = request.data.get("work_date") or date.today().isoformat()
        work_date_value = parse_date(str(raw_work_date))
        answers_payload = request.data.get("answers", [])

        if not team_id:
            return Response({"detail": "team is required."}, status=status.HTTP_400_BAD_REQUEST)
        if work_date_value is None:
            return Response(
                {"detail": "work_date must be a valid ISO date (YYYY-MM-DD)."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not isinstance(answers_payload, list) or not answers_payload:
            return Response(
                {"detail": "answers must be a non-empty list."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        team = get_object_or_404(StandupTeam, pk=team_id, company=company, is_active=True)

        checkin, _ = StandupCheckin.objects.get_or_create(
            company=company,
            team=team,
            member=employee,
            work_date=work_date_value,
            defaults={"created_by": request.user},
        )

        StandupAnswer.objects.filter(checkin=checkin).delete()
        blocker_count = 0

        team_questions = {
            question.id: question
            for question in StandupQuestion.objects.filter(team=team, is_active=True)
        }
        for item in answers_payload:
            question_id = item.get("question")
            body = (item.get("body") or "").strip()
            is_blocker = bool(item.get("is_blocker", False))

            if not question_id or question_id not in team_questions:
                return Response(
                    {"detail": f"Invalid question id: {question_id}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if not body:
                return Response(
                    {"detail": "Each answer requires a non-empty body."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            StandupAnswer.objects.create(
                checkin=checkin,
                question=team_questions[question_id],
                body=body,
                is_blocker=is_blocker,
            )
            if is_blocker:
                blocker_count += 1

        checkin.blocker_count = blocker_count
        checkin.save(update_fields=["blocker_count", "updated_at"])
        checkin.mark_submitted()
        checkin.refresh_from_db()
        serializer = self.get_serializer(checkin)
        return Response(serializer.data, status=status.HTTP_200_OK)


class StandupFollowViewSet(TenantScopedModelViewSet):
    queryset = StandupFollow.objects.select_related("team", "team__company", "follower").all().order_by("-created_at")
    serializer_class = StandupFollowSerializer
    company_filter_path = "team__company"
    search_fields = ["team__name", "follower__email"]
    ordering_fields = ["created_at"]

    def perform_create(self, serializer):
        serializer.save(follower=self.request.user)


class AuthContextView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses=inline_serializer(
            name="AuthContextResponse",
            fields={
                "user": inline_serializer(
                    name="AuthContextUser",
                    fields={
                        "id": drf_serializers.IntegerField(),
                        "email": drf_serializers.EmailField(),
                        "first_name": drf_serializers.CharField(),
                        "last_name": drf_serializers.CharField(),
                    },
                ),
                "active_company": inline_serializer(
                    name="AuthContextActiveCompany",
                    fields={
                        "id": drf_serializers.IntegerField(),
                        "name": drf_serializers.CharField(),
                        "slug": drf_serializers.CharField(),
                    },
                    allow_null=True,
                ),
                "memberships": CompanyMembershipSerializer(many=True),
            },
        )
    )
    def get(self, request):
        company = get_user_company(request.user)
        memberships = request.user.company_memberships.select_related("company").all()
        serializer = CompanyMembershipSerializer(memberships, many=True)
        return Response(
            {
                "user": {
                    "id": request.user.id,
                    "email": request.user.email,
                    "first_name": request.user.first_name,
                    "last_name": request.user.last_name,
                },
                "active_company": (
                    {"id": company.id, "name": company.name, "slug": company.slug}
                    if company
                    else None
                ),
                "memberships": serializer.data,
            }
        )


class SwitchCompanyView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=inline_serializer(
            name="SwitchCompanyRequest",
            fields={"company_id": drf_serializers.IntegerField()},
        ),
        responses=inline_serializer(
            name="SwitchCompanyResponse",
            fields={
                "detail": drf_serializers.CharField(),
                "active_company": inline_serializer(
                    name="SwitchCompanyActiveCompany",
                    fields={
                        "id": drf_serializers.IntegerField(),
                        "name": drf_serializers.CharField(),
                        "slug": drf_serializers.CharField(),
                    },
                ),
            },
        ),
    )
    def post(self, request):
        company_id = request.data.get("company_id")
        company = get_object_or_404(Company, pk=company_id, is_active=True)
        if not set_active_company(request.user, company):
            return Response(
                {"detail": "You do not have access to this company."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return Response(
            {
                "detail": "Active company updated.",
                "active_company": {
                    "id": company.id,
                    "name": company.name,
                    "slug": company.slug,
                },
            }
        )


class MyCompaniesView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses=inline_serializer(
            name="MyCompaniesResponse",
            fields={
                "results": inline_serializer(
                    name="MyCompanyItem",
                    fields={
                        "id": drf_serializers.IntegerField(),
                        "name": drf_serializers.CharField(),
                        "slug": drf_serializers.CharField(),
                    },
                    many=True,
                )
            },
        )
    )
    def get(self, request):
        companies = get_user_companies(request.user)
        data = [{"id": c.id, "name": c.name, "slug": c.slug} for c in companies]
        return Response({"results": data})
