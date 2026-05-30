from django.contrib.auth.views import LoginView
from django.contrib import messages
from django.shortcuts import redirect
from django.utils import timezone
from django.conf import settings

from accounting.mfa import (
    is_login_locked_out,
    record_login_failure,
    reset_login_attempts,
    get_remaining_attempts,
)


class RateLimitedLoginView(LoginView):
    template_name = "registration/login.html"

    def form_valid(self, form):
        user_identifier = form.cleaned_data.get("username") or self.request.POST.get("username", "")

        if is_login_locked_out(user_identifier):
            lockout_mins = getattr(settings, "LOGIN_LOCKOUT_SECONDS", 1800) // 60
            messages.error(
                self.request,
                f"Account temporarily locked due to too many failed attempts. Try again in {lockout_mins} minutes."
            )
            form.add_error(None, "Account temporarily locked.")
            return self.form_invalid(form)

        reset_login_attempts(user_identifier)
        return super().form_valid(form)

    def form_invalid(self, form):
        user_identifier = self.request.POST.get("username", "")
        if user_identifier:
            record_login_failure(user_identifier)
            remaining = get_remaining_attempts(user_identifier)
            if remaining == 0:
                lockout_mins = getattr(settings, "LOGIN_LOCKOUT_SECONDS", 1800) // 60
                messages.error(
                    self.request,
                    f"Too many failed attempts. Account locked for {lockout_mins} minutes."
                )
            else:
                messages.warning(
                    self.request,
                    f"Invalid credentials. {remaining} attempt(s) remaining."
                )
        return super().form_invalid(form)
