from django.urls import path

from projects import views

app_name = "projects"

urlpatterns = [
    path("", views.project_list, name="list"),
    path("new/", views.project_form, name="create"),
    path("<int:pk>/", views.project_detail, name="detail"),
    path("<int:pk>/edit/", views.project_form, name="edit"),
    path("tasks/<int:pk>/edit/", views.task_form, name="task_edit"),
    path("tasks/<int:pk>/status/", views.task_status, name="task_status"),
    path("timesheets/<int:timesheet_pk>/time/", views.timesheet_time, name="timesheet_time"),
    path("time/<int:pk>/delete/", views.time_entry_delete, name="time_entry_delete"),
    path("costs/", views.project_costs, name="costs"),
]
