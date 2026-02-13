from django.http import HttpResponseForbidden


class RoleBasedAccessMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.user.is_authenticated:
            return HttpResponseForbidden("Access Denied")

        # Example: Restrict access to admin-only views
        if (
            request.path.startswith("/admin/")
            and not request.user.groups.filter(name="Admin").exists()
        ):
            return HttpResponseForbidden("Access Denied")

        return self.get_response(request)
