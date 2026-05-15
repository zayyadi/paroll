from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from payroll import views as payroll_views
import importlib.util

# Custom error handlers
handler400 = "django.views.defaults.bad_request"
handler403 = "django.views.defaults.permission_denied"
handler404 = "django.views.defaults.page_not_found"
handler500 = "django.views.defaults.server_error"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", payroll_views.index, name="root"),
    path("marketing/", include("marketing.urls", namespace="marketing")),
    path("users/", include("users.urls", namespace="users")),
    # path("account/", include("django.contrib.auth.urls")),
    path("", include("payroll.urls", namespace="payroll")),
    path("accounting/", include("accounting.urls", namespace="accounting")),
    path("inventory/", include("inventory.urls", namespace="inventory")),
    # path(
    #     "__reload__/",
    #     include("django_browser_reload.urls"),
    # ),
]

if importlib.util.find_spec("rest_framework") and importlib.util.find_spec(
    "drf_spectacular"
):
    urlpatterns.append(path("api/", include("api.urls", namespace="api")))

if importlib.util.find_spec("social_django"):
    urlpatterns.append(path("oauth/", include("social_django.urls", namespace="social")))

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += staticfiles_urlpatterns()
