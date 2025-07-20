from django import views
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.urls import reverse
from django.contrib.auth.views import LoginView
from django.contrib import messages
from django.contrib.auth import logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import (
    AdminPasswordChangeForm,
    PasswordChangeForm,
    AuthenticationForm,
)
from django.contrib.auth.views import PasswordResetView, PasswordResetConfirmView
from django.urls import reverse_lazy
from django.template.loader import render_to_string
from django.utils.http import urlsafe_base64_encode
from django.contrib.sites.shortcuts import get_current_site  # For dynamic domain
from django.http import HttpResponseRedirect  # For returning from form_valid
from django.utils.encoding import force_bytes
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from core.settings import DEFAULT_FROM_EMAIL
from users.email_backend import send_mail as custom_send_mail

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

        return render(request, "registration/register.html", {"form": form})


class MyLoginView(LoginView):
    def get_success_url(self):
        redirect_url = self.request.GET.get("next")
        if redirect_url:
            return redirect_url

        return reverse("payroll:index")

    def form_valid(self, form):
        remember_me = self.request.POST.get("remember")
        if not remember_me:
            self.request.session.set_expiry(0)
            self.request.session.modified = True
        return super(MyLoginView, self).form_valid(form)


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
    email_template_name = "email/password_reset_email_custom.html"
    success_url = reverse_lazy("users:password_reset_done")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["site_name"] = get_current_site(self.request).name
        return context

    def send_mail(
        self,
        subject_template_name,
        email_template_name,
        context,
        from_email,
        to_email,
        html_email_template_name=None,
    ):
        subject = render_to_string(subject_template_name, context)
        subject = "".join(subject.splitlines())
        custom_send_mail(
            subject,
            email_template_name,
            context,
            from_email,
            [to_email],
            fail_silently=False,
        )

    def form_valid(self, form):
        # This method is overridden to use our custom send_mail function.
        # The original form.save() method calls send_mail internally.
        # We need to ensure our custom send_mail is used.
        # Django's PasswordResetForm.save() method expects a send_mail function
        # that takes specific arguments. Our custom_send_mail is designed to be compatible.

        # The default PasswordResetForm.save() method constructs the context
        # and calls the send_mail function. We need to replicate that logic
        # but use our custom_send_mail.

        # Get the user for whom the password reset is requested
        email = form.cleaned_data["email"]
        users = form.get_users(email)
        if not users:
            messages.error(self.request, "No user found with that email address.")
            return self.form_invalid(form)

        for user in users:
            current_site = get_current_site(self.request)
            site_name = current_site.name
            domain = current_site.domain
            protocol = "https" if self.request.is_secure() else "http"

            context = {
                "email": email,
                "domain": domain,
                "site_name": site_name,
                "uid": urlsafe_base64_encode(force_bytes(user.pk)),
                "user": user,
                "token": self.token_generator.make_token(user),
                "protocol": protocol,
                "reset_password_url": f"{protocol}://{domain}{reverse('users:password_reset_confirm', kwargs={'uidb64': urlsafe_base64_encode(force_bytes(user.pk)), 'token': self.token_generator.make_token(user)})}",
            }
            self.send_mail(
                "registration/password_reset_subject.txt",
                self.email_template_name,
                context,
                DEFAULT_FROM_EMAIL,
                user.email,
                html_email_template_name=self.email_template_name,
            )

        messages.success(
            self.request,
            "A password reset OTP has been sent to your email address. Please verify it to continue.",
        )
        return redirect(
            reverse("users:verify_password_reset_otp", kwargs={"email": email})
        )


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


from django.views.decorators.http import require_POST
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth.forms import PasswordResetForm
from django.core.cache import cache
import random
import string


def logout_view(request):
    logout(request)
    return render(request, "registration/logout.html")


def generate_otp():
    return "".join(random.choices(string.digits, k=6))


@login_required
def send_otp_view(request):
    user = request.user
    otp = generate_otp()
    cache.set(
        f"otp_{user.email}", otp, timeout=300
    )  # OTP valid for 5 minutes (300 seconds)
    context = {
        "user": user,
        "otp": otp,
    }
    custom_send_mail(
        "Your One-Time Password (OTP)",
        "email/otp_email.html",
        context,
        DEFAULT_FROM_EMAIL,
        [user.email],
    )
    messages.success(request, "An OTP has been sent to your email address.")
    return redirect("users:verify_otp")


@login_required
def verify_otp_view(request):
    if request.method == "POST":
        user_otp = request.POST.get("otp")
        user = request.user
        stored_otp = cache.get(f"otp_{user.email}")

        if stored_otp and stored_otp == user_otp:
            cache.delete(
                f"otp_{user.email}"
            )  # Invalidate OTP after successful verification
            messages.success(request, "OTP verified successfully.")
            return redirect("payroll:index")  # Redirect to a dashboard or success page
        else:
            messages.error(request, "Invalid or expired OTP.")
    return render(request, "registration/verify_otp.html")


class CustomRegisterView(RegisterView):
    def post(self, request):
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.is_active = False  # Deactivate account until email is verified
            user.save()

            current_site = get_current_site(request)
            subject = "Activate Your Payroll Account"

            # Generate OTP for registration confirmation
            otp = generate_otp()
            cache.set(
                f"registration_otp_{user.email}", otp, timeout=600
            )  # OTP valid for 10 minutes

            context = {
                "user": user,
                "domain": current_site.domain,
                "uid": urlsafe_base64_encode(force_bytes(user.pk)),
                "token": self.token_generator.make_token(
                    user
                ),  # This token is for password reset, not direct activation
                "login_url": f"{request.scheme}://{current_site.domain}{reverse('users:login')}",
                "otp": otp,  # Pass OTP to the template
            }

            custom_send_mail(
                subject,
                "email/registration_email.html",  # Use a template that includes OTP
                context,
                DEFAULT_FROM_EMAIL,
                [user.email],
            )
            messages.success(
                request,
                "Please confirm your email address with the OTP sent to your email to complete the registration.",
            )
            return redirect(
                reverse("users:verify_registration_otp", kwargs={"email": user.email})
            )
        return render(request, "registration/register.html", {"form": form})


def verify_registration_otp_view(request, email):
    user = CustomUser.objects.get(email=email)
    if request.method == "POST":
        user_otp = request.POST.get("otp")
        stored_otp = cache.get(f"registration_otp_{user.email}")

        if stored_otp and stored_otp == user_otp:
            cache.delete(f"registration_otp_{user.email}")
            user.is_active = True
            user.save()
            messages.success(
                request, "Email verified successfully. You can now log in."
            )
            return redirect("users:login")
        else:
            messages.error(request, "Invalid or expired OTP.")
    return render(
        request, "registration/verify_registration_otp.html", {"email": email}
    )


class CustomPasswordResetForm(PasswordResetForm):
    def get_users(self, email):
        """Given an email, return matching users who should receive a reset email."""
        active_users = CustomUser._default_manager.filter(
            email__iexact=email, is_active=True
        )
        return (u for u in active_users if u.has_usable_password())

    def save(
        self,
        domain_override=None,
        subject_template_name="registration/password_reset_subject.txt",
        email_template_name="email/password_reset_email_custom.html",
        use_https=False,
        token_generator=None,
        from_email=None,
        request=None,
        html_email_template_name=None,
        extra_email_context=None,
    ):
        """
        Generates a one-use only link for resetting password and sends to the user.
        """
        if not token_generator:
            from django.contrib.auth.tokens import default_token_generator

            token_generator = default_token_generator

        for user in self.get_users(self.cleaned_data["email"]):
            if not domain_override:
                current_site = get_current_site(request)
                site_name = current_site.name
                domain = current_site.domain
            else:
                site_name = domain = domain_override

            # Generate OTP for password reset confirmation
            otp = generate_otp()
            cache.set(
                f"password_reset_otp_{user.email}", otp, timeout=600
            )  # OTP valid for 10 minutes

            context = {
                "email": user.email,
                "domain": domain,
                "site_name": site_name,
                "uid": urlsafe_base64_encode(force_bytes(user.pk)),
                "user": user,
                "token": token_generator.make_token(user),
                "protocol": "https" if use_https else "http",
                "otp": otp,  # Pass OTP to the template
                **(extra_email_context or {}),
            }

            custom_send_mail(
                render_to_string(subject_template_name, context),
                email_template_name,
                context,
                from_email,
                [user.email],
                html_email_template_name=html_email_template_name,
            )

        # Instead of redirecting to password_reset_done, we'll redirect to a new OTP verification page
        # for password reset. This requires a change in CustomPasswordResetView.
        # For now, we'll let the view handle the redirect.
