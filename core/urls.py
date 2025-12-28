from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.staticfiles.urls import staticfiles_urlpatterns

# Custom error handlers
handler400 = "django.views.defaults.bad_request"
handler403 = "django.views.defaults.permission_denied"
handler404 = "django.views.defaults.page_not_found"
handler500 = "django.views.defaults.server_error"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("users/", include("users.urls", namespace="users")),
    # path("account/", include("django.contrib.auth.urls")),
    path("", include("payroll.urls", namespace="payroll")),
    path("accounting/", include("accounting.urls", namespace="accounting")),
    path("api/", include("api.urls", namespace="api")),
    path("oauth/", include("social_django.urls", namespace="social")),
    # path(
    #     "__reload__/",
    #     include("django_browser_reload.urls"),
    # ),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += staticfiles_urlpatterns()
