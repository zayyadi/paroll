from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter

from api.v1.viewsets import (
    AccountViewSet,
    AccountingPeriodViewSet,
    AuthContextView,
    DepartmentViewSet,
    EmployeeViewSet,
    FiscalYearViewSet,
    IOUViewSet,
    JournalEntryViewSet,
    JournalViewSet,
    LeavePolicyViewSet,
    LeaveRequestViewSet,
    MyCompaniesView,
    PayrollEntryViewSet,
    PayrollRunEntryViewSet,
    PayrollRunViewSet,
    PayrollViewSet,
    StandupCheckinViewSet,
    StandupFollowViewSet,
    StandupQuestionViewSet,
    StandupTeamMemberViewSet,
    StandupTeamViewSet,
    SwitchCompanyView,
)


app_name = "v1"

router = DefaultRouter()
router.register(r"departments", DepartmentViewSet, basename="department")
router.register(r"employees", EmployeeViewSet, basename="employee")
router.register(r"payrolls", PayrollViewSet, basename="payroll")
router.register(r"payroll-entries", PayrollEntryViewSet, basename="payroll-entry")
router.register(r"payroll-runs", PayrollRunViewSet, basename="payroll-run")
router.register(
    r"payroll-run-entries", PayrollRunEntryViewSet, basename="payroll-run-entry"
)
router.register(r"leave-policies", LeavePolicyViewSet, basename="leave-policy")
router.register(r"leave-requests", LeaveRequestViewSet, basename="leave-request")
router.register(r"ious", IOUViewSet, basename="iou")
router.register(r"standup-teams", StandupTeamViewSet, basename="standup-team")
router.register(r"standup-team-members", StandupTeamMemberViewSet, basename="standup-team-member")
router.register(r"standup-questions", StandupQuestionViewSet, basename="standup-question")
router.register(r"standup-checkins", StandupCheckinViewSet, basename="standup-checkin")
router.register(r"standup-follows", StandupFollowViewSet, basename="standup-follow")

router.register(r"accounts", AccountViewSet, basename="account")
router.register(r"fiscal-years", FiscalYearViewSet, basename="fiscal-year")
router.register(r"accounting-periods", AccountingPeriodViewSet, basename="accounting-period")
router.register(r"journals", JournalViewSet, basename="journal")
router.register(r"journal-entries", JournalEntryViewSet, basename="journal-entry")

urlpatterns = [
    path("auth/context/", AuthContextView.as_view(), name="auth-context"),
    path("auth/switch-company/", SwitchCompanyView.as_view(), name="switch-company"),
    path("auth/companies/", MyCompaniesView.as_view(), name="my-companies"),
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path("docs/swagger/", SpectacularSwaggerView.as_view(url_name="api:v1:schema"), name="swagger-ui"),
    path("docs/redoc/", SpectacularRedocView.as_view(url_name="api:v1:schema"), name="redoc"),
    path("", include(router.urls)),
]

try:
    from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

    urlpatterns = [
        path("auth/token/", TokenObtainPairView.as_view(), name="token-obtain-pair"),
        path(
            "auth/token/refresh/",
            TokenRefreshView.as_view(),
            name="token-refresh",
        ),
        *urlpatterns,
    ]
except ImportError:
    # JWT routes are exposed automatically when simplejwt is installed.
    pass
