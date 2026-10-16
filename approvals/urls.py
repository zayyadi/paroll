from django.urls import path
from . import views

app_name = "approvals"
urlpatterns = [
    path("", views.inbox, name="inbox"),
    path("policies/", views.policies, name="policies"),
    path("policies/<int:pk>/", views.policies, name="policy_edit"),
    path("<int:pk>/", views.detail, name="detail"),
    path("<int:pk>/approve/", views.decision, {"operation": "approve"}, name="approve"),
    path("<int:pk>/reject/", views.decision, {"operation": "reject"}, name="reject"),
    path("<int:pk>/cancel/", views.decision, {"operation": "cancel"}, name="cancel"),
]
