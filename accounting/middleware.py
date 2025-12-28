"""
Middleware to capture user information and request context for audit trail entries.
This middleware stores request metadata in thread-local storage for access by signal handlers.
"""

import threading
from django.utils.deprecation import MiddlewareMixin
from django.http import HttpRequest
from django.contrib.auth import get_user_model
from ipaddress import ip_address

# Thread-local storage for request context
_thread_locals = threading.local()


def get_request_user():
    """
    Get the current user from thread-local storage.

    Returns:
        User instance or None if not available
    """
    return getattr(_thread_locals, "user", None)


def get_request_metadata():
    """
    Get request metadata from thread-local storage.

    Returns:
        Tuple of (ip_address, user_agent) or (None, None) if not available
    """
    return (
        getattr(_thread_locals, "ip_address", None),
        getattr(_thread_locals, "user_agent", None),
    )


def get_request_object():
    """
    Get the current request object from thread-local storage.

    Returns:
        HttpRequest instance or None if not available
    """
    return getattr(_thread_locals, "request", None)


class AuditTrailMiddleware(MiddlewareMixin):
    """
    Middleware to capture request context for audit trail logging.

    This middleware extracts and stores:
    - Current user
    - IP address
    - User agent
    - Request object

    The information is stored in thread-local storage and can be accessed
    by signal handlers and other parts of the application.
    """

    def process_request(self, request):
        """
        Store request context in thread-local storage.

        Args:
            request: HttpRequest object

        Returns:
            None - Continue processing the request
        """
        # Store the request object
        _thread_locals.request = request

        # Store user information
        if hasattr(request, "user") and request.user.is_authenticated:
            _thread_locals.user = request.user
        else:
            _thread_locals.user = None

        # Extract IP address
        _thread_locals.ip_address = self.get_client_ip(request)

        # Extract user agent
        _thread_locals.user_agent = request.META.get("HTTP_USER_AGENT", "")

        return None

    def process_response(self, request, response):
        """
        Clean up thread-local storage after request processing.

        Args:
            request: HttpRequest object
            response: HttpResponse object

        Returns:
            HttpResponse object - Continue with response
        """
        # Clean up thread-local storage
        if hasattr(_thread_locals, "request"):
            delattr(_thread_locals, "request")
        if hasattr(_thread_locals, "user"):
            delattr(_thread_locals, "user")
        if hasattr(_thread_locals, "ip_address"):
            delattr(_thread_locals, "ip_address")
        if hasattr(_thread_locals, "user_agent"):
            delattr(_thread_locals, "user_agent")

        return response

    def get_client_ip(self, request):
        """
        Extract the client's IP address from the request.

        This method handles various proxy configurations and load balancers
        by checking multiple headers in order of preference.

        Args:
            request: HttpRequest object

        Returns:
            String representation of IP address or None if not found
        """
        # List of headers to check in order of preference
        headers_to_check = [
            "HTTP_X_FORWARDED_FOR",
            "HTTP_X_REAL_IP",
            "HTTP_CLIENT_IP",
            "REMOTE_ADDR",
        ]

        ip = None

        for header in headers_to_check:
            value = request.META.get(header)
            if value:
                # X-Forwarded-For can contain multiple IPs, take the first one
                if header == "HTTP_X_FORWARDED_FOR":
                    ip = value.split(",")[0].strip()
                else:
                    ip = value.strip()
                break

        if ip:
            try:
                # Validate IP address format
                ip_obj = ip_address(ip)
                return str(ip_obj)
            except ValueError:
                # Invalid IP format, continue to next header
                pass

        return None


class SystemUserMiddleware(MiddlewareMixin):
    """
    Middleware to provide a system user for background operations.

    This is useful for operations that don't have a direct user context,
    such as cron jobs, management commands, or system-generated transactions.
    """

    def process_request(self, request):
        """
        Set up system user context if no user is authenticated.

        Args:
            request: HttpRequest object

        Returns:
            None - Continue processing the request
        """
        # Only set system user if no user is already authenticated
        if not hasattr(request, "user") or not request.user.is_authenticated:
            try:
                User = get_user_model()
                system_user = User.objects.filter(username="system").first()
                if system_user:
                    _thread_locals.user = system_user
            except Exception:
                # Silently fail if we can't get the system user
                pass

        return None


def get_audit_context():
    """
    Get complete audit context from thread-local storage.

    Returns:
        Dictionary with audit context information
    """
    return {
        "user": get_request_user(),
        "ip_address": getattr(_thread_locals, "ip_address", None),
        "user_agent": getattr(_thread_locals, "user_agent", None),
        "request": get_request_object(),
    }


def set_audit_user(user):
    """
    Manually set the audit user in thread-local storage.

    This is useful for management commands or background tasks
    where you want to override the automatic user detection.

    Args:
        user: User instance to set as current user
    """
    _thread_locals.user = user


def set_audit_metadata(ip_address=None, user_agent=None):
    """
    Manually set audit metadata in thread-local storage.

    Args:
        ip_address: IP address string
        user_agent: User agent string
    """
    if ip_address is not None:
        _thread_locals.ip_address = ip_address
    if user_agent is not None:
        _thread_locals.user_agent = user_agent


def clear_audit_context():
    """
    Clear all audit context from thread-local storage.

    This is useful for testing or when you want to ensure
    that no audit context is carried over between operations.
    """
    if hasattr(_thread_locals, "request"):
        delattr(_thread_locals, "request")
    if hasattr(_thread_locals, "user"):
        delattr(_thread_locals, "user")
    if hasattr(_thread_locals, "ip_address"):
        delattr(_thread_locals, "ip_address")
    if hasattr(_thread_locals, "user_agent"):
        delattr(_thread_locals, "user_agent")
