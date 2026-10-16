from django.urls import path
from .api import Inbox, Detail, Decide, Cancel, Submit

app_name = "approval_api"
urlpatterns = [
    path("", Inbox.as_view(), name="inbox"),
    path("submit/", Submit.as_view(), name="submit"),
    path("<int:pk>/", Detail.as_view(), name="detail"),
    path("<int:pk>/decide/", Decide.as_view(), name="decide"),
    path("<int:pk>/cancel/", Cancel.as_view(), name="cancel"),
]
