"""Discipline module URLs."""

from django.urls import path

from . import views

app_name = "discipline"

urlpatterns = [
    path("system/", views.disciplinary_system_view, name="system"),
    path("cases/", views.DisciplinaryCaseListView.as_view(), name="case_list"),
    path("cases/new/", views.DisciplinaryCaseCreateView.as_view(), name="case_create"),
    path("cases/<int:pk>/", views.DisciplinaryCaseDetailView.as_view(), name="case_detail"),
    path(
        "cases/<int:pk>/edit/",
        views.DisciplinaryCaseUpdateView.as_view(),
        name="case_update",
    ),
    path(
        "cases/<int:pk>/start-investigation/",
        views.disciplinary_case_start_investigation,
        name="case_start_investigation",
    ),
    path(
        "cases/<int:pk>/evidence/add/",
        views.DisciplinaryEvidenceCreateView.as_view(),
        name="evidence_create",
    ),
    path(
        "cases/<int:pk>/decision/",
        views.DisciplinaryDecisionUpdateView.as_view(),
        name="decision_update",
    ),
    path(
        "cases/<int:pk>/sanction/add/",
        views.DisciplinarySanctionCreateView.as_view(),
        name="sanction_create",
    ),
    path(
        "cases/<int:pk>/appeal/add/",
        views.DisciplinaryAppealCreateView.as_view(),
        name="appeal_create",
    ),
    path(
        "appeals/<int:pk>/review/",
        views.DisciplinaryAppealReviewView.as_view(),
        name="appeal_review",
    ),
]
