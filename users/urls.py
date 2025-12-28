from django.urls import path
from users import views

# from django.contrib.auth.views import PasswordResetView, PasswordResetConfirmView

app_name = "users"


urlpatterns = [
    path("register", views.CustomRegisterView.as_view(), name="register"),
    path("send_otp/", views.send_otp_view, name="send_otp"),
    path("verify_otp/", views.verify_otp_view, name="verify_otp"),
    path(
        "verify_registration_otp/<str:email>/",
        views.verify_registration_otp_view,
        name="verify_registration_otp",
    ),
    # path(
    #     "verify_password_reset_otp/<str:email>/",
    #     views.verify_password_reset_otp_view,
    #     name="verify_password_reset_otp",
    # ),
    path(
        "password_reset/",
        views.CustomPasswordResetView.as_view(form_class=views.CustomPasswordResetForm),
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
    path("password", views.password, name="password"),
    path("login", views.MyLoginView.as_view(), name="login"),
    path("socials", views.social_login, name="socials"),
    path("logout", views.logout_view, name="logout"),
]
