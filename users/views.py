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
)
from django.contrib.auth.forms import PasswordResetForm
from django.core.cache import cache
from django.conf import settings
import random
import string
import logging
from django.contrib.auth.views import PasswordResetView, PasswordResetConfirmView
from django.urls import reverse_lazy
from django.template.loader import render_to_string
from django.utils.http import urlsafe_base64_encode
from django.utils.http import urlsafe_base64_decode
from django.utils.http import url_has_allowed_host_and_scheme
from django.contrib.sites.shortcuts import get_current_site  # For dynamic domain
from django.contrib.auth.tokens import default_token_generator

# from django.http import HttpResponseRedirect  # For returning from form_valid
from django.utils.encoding import force_bytes
from django.utils.encoding import force_str

# from django.utils.encoding import force_str
# from django.utils.http import urlsafe_base64_decode
from core.settings import DEFAULT_FROM_EMAIL
from users.email_backend import send_mail as custom_send_mail

from social_django.models import UserSocialAuth

from users.forms import SignUpForm
from users.models import CustomUser
from company.models import Company
from company.utils import set_active_company

logger = logging.getLogger(__name__)


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
    template_name = "registration/login_new.html"

    def _resolve_login_company(self, user):
        if settings.MULTI_COMPANY_MEMBERSHIP_ENABLED:
            memberships = user.company_memberships.select_related("company").filter(
                company__is_active=True
            )
            if memberships.exists():
                active_company = getattr(user, "active_company", None)
                if active_company and memberships.filter(company=active_company).exists():
                    return active_company

                default_membership = memberships.filter(is_default=True).first()
                if default_membership:
                    return default_membership.company

                if user.company_id and memberships.filter(company=user.company).exists():
                    return user.company

                return memberships.first().company

            if user.company and user.company.is_active:
                return user.company

            if user.active_company and user.active_company.is_active:
                return user.active_company

            return None

        company = user.company or user.active_company
        if company and getattr(company, "is_active", True):
            return company
        return None

    def get_success_url(self):
        redirect_url = self.request.POST.get(self.redirect_field_name) or self.request.GET.get(
            self.redirect_field_name
        )
        if redirect_url and url_has_allowed_host_and_scheme(
            redirect_url,
            allowed_hosts={self.request.get_host()},
            require_https=self.request.is_secure(),
        ):
            return redirect_url

        return reverse("payroll:index")

    def form_valid(self, form):
        user = form.get_user()
        company = self._resolve_login_company(user)
        if company is None:
            form.add_error(
                None,
                "Your account is not assigned to an active company. Contact your administrator.",
            )
            return self.form_invalid(form)

        update_fields = []
        if not user.company_id:
            user.company = company
            update_fields.append("company")
        if user.active_company_id != company.id:
            user.active_company = company
            update_fields.append("active_company")
        if update_fields:
            user.save(update_fields=update_fields)

        remember_me = self.request.POST.get("remember")
        if not remember_me:
            self.request.session.set_expiry(0)
            self.request.session.modified = True
        return super(MyLoginView, self).form_valid(form)


def social_login(request):
    return render(request, "registration/socials.html")


@login_required
def settings_view(request):
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
        users = list(form.get_users(email))

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

        messages.success(self.request, "If the account exists, reset instructions were sent.")
        return redirect(reverse("users:password_reset_done"))


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


def generate_otp():
    return "".join(random.choices(string.digits, k=6))


def _get_client_ip(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")


def _otp_attempts_key(flow: str, email: str, ip: str) -> str:
    return f"otp_attempts:{flow}:{email.lower()}:{ip}"


def _otp_lock_key(flow: str, email: str, ip: str) -> str:
    return f"otp_lock:{flow}:{email.lower()}:{ip}"


def _is_otp_locked(flow: str, email: str, ip: str) -> bool:
    return bool(cache.get(_otp_lock_key(flow, email, ip)))


def _record_failed_otp_attempt(flow: str, email: str, ip: str):
    max_attempts = int(getattr(settings, "OTP_MAX_ATTEMPTS", 5))
    window_seconds = int(getattr(settings, "OTP_ATTEMPT_WINDOW_SECONDS", 600))
    lockout_seconds = int(getattr(settings, "OTP_LOCKOUT_SECONDS", 900))
    key = _otp_attempts_key(flow, email, ip)
    attempts = int(cache.get(key, 0)) + 1
    cache.set(key, attempts, timeout=window_seconds)
    if attempts >= max_attempts:
        cache.set(_otp_lock_key(flow, email, ip), 1, timeout=lockout_seconds)


def _clear_otp_attempts(flow: str, email: str, ip: str):
    cache.delete(_otp_attempts_key(flow, email, ip))
    cache.delete(_otp_lock_key(flow, email, ip))


def send_registration_activation_email(request, user):
    otp_timeout = getattr(settings, "REGISTRATION_OTP_TIMEOUT_SECONDS", 600)
    otp = generate_otp()
    cache.set(f"registration_otp_{user.email}", otp, timeout=otp_timeout)

    current_site = get_current_site(request)
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    context = {
        "user": user,
        "first_name": user.first_name or user.email,
        "domain": current_site.domain,
        "uid": uid,
        "token": token,
        "login_url": f"{request.scheme}://{current_site.domain}{reverse('users:login')}",
        "activation_url": f"{request.scheme}://{current_site.domain}{reverse('users:activate', kwargs={'uidb64': uid, 'token': token})}",
        "otp": otp,
    }

    custom_send_mail(
        "Activate Your Payroll Account",
        "email/registration_email.html",
        context,
        DEFAULT_FROM_EMAIL,
        [user.email],
    )


def get_resend_limit_status(email):
    cooldown_seconds = getattr(settings, "REGISTRATION_RESEND_COOLDOWN_SECONDS", 60)
    max_per_hour = getattr(settings, "REGISTRATION_RESEND_MAX_PER_HOUR", 5)
    cooldown_key = f"registration_resend_cooldown_{email}"
    count_key = f"registration_resend_count_{email}"

    if cache.get(cooldown_key):
        return False, (
            f"Please wait {cooldown_seconds} seconds before requesting another "
            "activation email."
        )

    resend_count = int(cache.get(count_key, 0))
    if resend_count >= max_per_hour:
        return (
            False,
            "Activation email resend limit reached. Please wait up to an hour.",
        )

    cache.set(cooldown_key, 1, timeout=cooldown_seconds)
    cache.set(count_key, resend_count + 1, timeout=3600)
    return True, None


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
    user = request.user
    ip = _get_client_ip(request)
    flow = "session_otp"
    email = user.email

    if _is_otp_locked(flow, email, ip):
        messages.error(request, "Too many attempts. Please try again later.")
        return render(request, "registration/verify_otp.html")

    if request.method == "POST":
        user_otp = request.POST.get("otp")
        stored_otp = cache.get(f"otp_{user.email}")

        if stored_otp and stored_otp == user_otp:
            cache.delete(
                f"otp_{user.email}"
            )  # Invalidate OTP after successful verification
            _clear_otp_attempts(flow, email, ip)
            messages.success(request, "OTP verified successfully.")
            return redirect("payroll:index")  # Redirect to a dashboard or success page
        else:
            _record_failed_otp_attempt(flow, email, ip)
            messages.error(request, "Invalid or expired OTP.")
    return render(request, "registration/verify_otp.html")


class CustomRegisterView(RegisterView):
    token_generator = default_token_generator

    def post(self, request):
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.is_active = False  # Deactivate account until email is verified
            user.save()
            send_registration_activation_email(request, user)
            messages.success(
                request,
                "Activation link sent to your email. You can use the OTP as fallback if needed.",
            )
            return redirect(
                reverse("users:verify_registration_otp", kwargs={"email": user.email})
            )
        return render(request, "registration/register.html", {"form": form})


def verify_registration_otp_view(request, email):
    ip = _get_client_ip(request)
    flow = "registration"

    if _is_otp_locked(flow, email, ip):
        messages.error(request, "Too many attempts. Please try again later.")
        return render(
            request, "registration/verify_registration_otp.html", {"email": email}
        )

    user = CustomUser.objects.filter(email=email).first()

    if request.method == "POST":
        user_otp = request.POST.get("otp")
        stored_otp = cache.get(f"registration_otp_{email}")

        if user and (not user.is_active) and stored_otp and stored_otp == user_otp:
            cache.delete(f"registration_otp_{email}")
            _clear_otp_attempts(flow, email, ip)
            user.is_active = True
            user.save(update_fields=["is_active"])
            logger.info("Registration OTP verified for user_id=%s", user.id)
            messages.success(
                request, "Email verified successfully. You can now log in."
            )
            return redirect("users:login")
        else:
            _record_failed_otp_attempt(flow, email, ip)
            logger.warning(
                "Invalid registration OTP attempt for email=%s ip=%s",
                email,
                request.META.get("REMOTE_ADDR"),
            )
            messages.error(request, "Invalid or expired OTP.")
    return render(
        request, "registration/verify_registration_otp.html", {"email": email}
    )


def activate_account_view(request, uidb64, token):
    user = None
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = CustomUser.objects.filter(pk=uid).first()
    except (TypeError, ValueError, OverflowError):
        user = None

    if user and default_token_generator.check_token(user, token):
        if not user.is_active:
            user.is_active = True
            user.save(update_fields=["is_active"])
            logger.info("Account activated by token for user_id=%s", user.id)
        cache.delete(f"registration_otp_{user.email}")
        messages.success(request, "Account activated. You can now log in.")
        return redirect("users:login")
    if user and user.is_active:
        messages.info(request, "This account is already active. Please log in.")
        return redirect("users:login")

    timeout_seconds = getattr(settings, "PASSWORD_RESET_TIMEOUT", 60 * 60 * 24 * 3)
    logger.warning(
        "Invalid activation token for uidb64=%s ip=%s",
        uidb64,
        request.META.get("REMOTE_ADDR"),
    )
    return render(
        request,
        "registration/account_activation_invalid.html",
        {"expiry_minutes": timeout_seconds // 60},
        status=400,
    )


def resend_registration_activation_view(request, email):
    if request.method != "POST":
        return redirect(reverse("users:verify_registration_otp", kwargs={"email": email}))

    user = CustomUser.objects.filter(email=email).first()
    if user and not user.is_active:
        allowed, message = get_resend_limit_status(email)
        if not allowed:
            messages.error(request, message)
            return redirect(reverse("users:verify_registration_otp", kwargs={"email": email}))

        send_registration_activation_email(request, user)
        logger.info("Resent activation email for user_id=%s", user.id)

    messages.success(
        request,
        "If the account exists and is pending activation, a new activation email was sent.",
    )
    return redirect(reverse("users:verify_registration_otp", kwargs={"email": email}))


@login_required
def switch_company_view(request, company_id):
    if request.method != "POST":
        return redirect("payroll:index")

    if not settings.MULTI_COMPANY_MEMBERSHIP_ENABLED:
        messages.error(request, "Company switching is not enabled.")
        return redirect("payroll:index")

    company = Company.objects.filter(id=company_id, is_active=True).first()
    if company is None:
        messages.error(request, "Company not found.")
        return redirect("payroll:index")

    if set_active_company(request.user, company):
        messages.success(request, f"Switched to {company.name}.")
    else:
        messages.error(request, "You do not have access to that company.")
    return redirect("payroll:index")


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
