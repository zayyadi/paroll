from django import views
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.urls import reverse
from django.contrib.auth.views import LoginView
from django.contrib import messages
from django.contrib.auth import logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AdminPasswordChangeForm, PasswordChangeForm
from django.contrib.auth.views import PasswordResetView, PasswordResetConfirmView
from django.urls import reverse_lazy
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from core.settings import DEFAULT_FROM_EMAIL

from social_django.models import UserSocialAuth

from users.forms import SignUpForm
from users.models import CustomUser


class RegisterView(views.View):
    def get(self, request):
        return render(request, "registration/register.html", {"form": SignUpForm()})

    def post(self, request):
        form = SignUpForm(request.POST)
        if form.is_valid():
            form.save()

            return redirect(reverse("users:login"))

        return render(request, "register.html", {"form": form})


class MyLoginView(LoginView):
    def get_success_url(self):
        redirect_url = self.request.GET.get("next")
        if redirect_url:
            return redirect_url

        return reverse("payroll:index")


def social_login(request):
    return render(request, "registration/socials.html")


@login_required
def settings(request):
    user = request.user

    try:
        github_login = user.social_auth.get(provider="github")
    except UserSocialAuth.DoesNotExist:
        github_login = None

    try:
        twitter_login = user.social_auth.get(provider="twitter")
    except UserSocialAuth.DoesNotExist:
        twitter_login = None

    try:
        facebook_login = user.social_auth.get(provider="facebook")
    except UserSocialAuth.DoesNotExist:
        facebook_login = None

    can_disconnect = user.social_auth.count() > 1 or user.has_usable_password()

    return render(
        request,
        "registration/settings.html",
        {
            "github_login": github_login,
            "twitter_login": twitter_login,
            "facebook_login": facebook_login,
            "can_disconnect": can_disconnect,
        },
    )


@login_required
def password(request):
    if request.user.has_usable_password():
        PasswordForm = PasswordChangeForm
    else:
        PasswordForm = AdminPasswordChangeForm

    if request.method == "POST":
        form = PasswordForm(request.user, request.POST)
        if form.is_valid():
            form.save()
            update_session_auth_hash(request, form.user)
            messages.success(request, "Your password was successfully updated!")
            return redirect("password")
        else:
            messages.error(request, "Please correct the error below.")
    else:
        form = PasswordForm(request.user)
    return render(request, "users/password.html", {"form": form})


def validate_username(request):
    """Check username availability"""
    username = request.GET.get("email", None)
    response = {"is_taken": CustomUser.objects.filter(email__iexact=username).exists()}
    return JsonResponse(response)


class CustomPasswordResetView(PasswordResetView):
    email_template_name = "registration/password_reset_email.html"
    success_url = reverse_lazy("users:password_reset_done")

    def send_mail(
        self,
        subject_template_name,
        email_template_name,
        context,
        from_email,
        to_email,
        html_email_template_name=None,
    ):
        # Access the user instance and include it in the context
        context["user"] = self.user
        super().send_mail(
            subject_template_name,
            email_template_name,
            context,
            from_email,
            to_email,
            html_email_template_name,
        )

    def form_valid(self, form):
        response = super().form_valid(form)
        uidb64 = urlsafe_base64_encode(force_bytes(self.user.id))
        token = self.object.token
        reset_url = reverse(
            "users:password_reset_confirm", kwargs={"uidb64": uidb64, "token": token}
        )
        email_body = render_to_string(
            "registration/password_reset_email.html",
            {
                "protocol": "http",  # or 'https' depending on your setup
                "domain": "127.0.0.1",  # replace with your actual domain
                "uidb64": uidb64,
                "token": token,
                "reset_url": reset_url,
                "user": self.user,  # include the user instance in the context
            },
        )
        send_mail("Password Reset", email_body, DEFAULT_FROM_EMAIL, [self.user.email])
        messages.success(self.request, "Password reset email sent successfully.")
        return response


class CustomPasswordResetConfirmView(PasswordResetConfirmView):
    success_url = reverse_lazy("users:password_reset_complete")

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Password successfully reset.")
        return response


def custom_password_reset_done(request):
    # Your custom password reset done view logic
    return render(request, "registration/password_reset_done.html")


def custom_password_reset_complete(request):
    # Your custom password reset complete view logic
    return render(request, "registration/password_reset_complete.html")


def logout_view(request):
    logout(request)
    return render(request, "registration/logout.html")
