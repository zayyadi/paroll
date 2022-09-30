from django.urls import path

from employee import views

app_name = 'employee'

urlpatterns = [
    path('', views.add_employee, name='employee'),
]