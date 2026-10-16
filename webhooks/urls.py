from django.urls import path

from webhooks.views import changed_employees

app_name = "webhooks"

urlpatterns = [
    path("changed-employees/", changed_employees, name="changed-employees"),
]
