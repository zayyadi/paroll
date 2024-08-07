from django.urls import path
from users import views

# from django.contrib.auth.views import PasswordResetView, PasswordResetConfirmView

app_name = "users"


urlpatterns = [
    path("register", views.RegisterView.as_view(), name="register"),
    path(
        "password_reset/",
        views.CustomPasswordResetView.as_view(),
        name="password_reset",
    ),
    path(
        "password_reset/done/",
        views.custom_password_reset_done,
        name="password_reset_done",
    ),
    path(
        "password_reset/complete/",
        views.custom_password_reset_complete,
        name="password_reset_complete",
    ),
    path(
        "password_reset/<uidb64>/<token>/",
        views.CustomPasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
    path("login", views.MyLoginView.as_view(), name="login"),
    path("socials", views.social_login, name="socials"),
    path("logout", views.logout_view, name="logout"),
]
