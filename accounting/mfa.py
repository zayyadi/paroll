from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.conf import settings
from functools import wraps
import time


# Auth-level security keys (login lockout, MFA step-up) are account-scoped,
# not tenant data: they deliberately do NOT go through tenant_cache_key.
# Prefixing them per company would let a locked-out user simply switch
# companies to reset the control.
def get_login_attempts_cache_key(user_identifier):
    return f"login_attempts:{user_identifier}"


def get_login_lockout_cache_key(user_identifier):
    return f"login_lockout:{user_identifier}"


MAX_LOGIN_ATTEMPTS = getattr(settings, "LOGIN_MAX_ATTEMPTS", 5)
LOGIN_ATTEMPT_WINDOW = getattr(settings, "LOGIN_ATTEMPT_WINDOW_SECONDS", 900)
LOGIN_LOCKOUT_SECONDS = getattr(settings, "LOGIN_LOCKOUT_SECONDS", 1800)


def record_login_failure(user_identifier):
    key = get_login_attempts_cache_key(user_identifier)
    attempts = cache.get(key, 0)
    attempts += 1
    cache.set(key, attempts, timeout=LOGIN_ATTEMPT_WINDOW)

    if attempts >= MAX_LOGIN_ATTEMPTS:
        lockout_key = get_login_lockout_cache_key(user_identifier)
        cache.set(lockout_key, True, timeout=LOGIN_LOCKOUT_SECONDS)
        return False

    return True


def is_login_locked_out(user_identifier):
    lockout_key = get_login_lockout_cache_key(user_identifier)
    return bool(cache.get(lockout_key, False))


def reset_login_attempts(user_identifier):
    key = get_login_attempts_cache_key(user_identifier)
    cache.delete(key)
    lockout_key = get_login_lockout_cache_key(user_identifier)
    cache.delete(lockout_key)


def get_remaining_attempts(user_identifier):
    key = get_login_attempts_cache_key(user_identifier)
    attempts = cache.get(key, 0)
    return max(0, MAX_LOGIN_ATTEMPTS - attempts)


def require_mfa_step_up(view_func):
    """Decorator requiring recent MFA verification for sensitive operations.

    Use on views handling posting journals, closing periods, approving
    reconciliations, or other high-risk accounting actions.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        mfa_key = f"mfa_verified:{request.user.pk}"
        verified_at = cache.get(mfa_key)
        mfa_timeout = getattr(settings, "MFA_STEP_UP_TIMEOUT", 900)

        if verified_at and (time.time() - verified_at) < mfa_timeout:
            return view_func(request, *args, **kwargs)

        request.session["mfa_return_url"] = request.get_full_path()
        from django.shortcuts import redirect
        return redirect("mfa_verify")

    return _wrapped_view


def mark_mfa_verified(user):
    mfa_key = f"mfa_verified:{user.pk}"
    cache.set(mfa_key, time.time(), timeout=getattr(settings, "MFA_STEP_UP_TIMEOUT", 900))
