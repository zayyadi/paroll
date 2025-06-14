from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static


urlpatterns = [
    path("admin/", admin.site.urls),
    path("users/", include("users.urls", namespace="users")),
    # path("account/", include("django.contrib.auth.urls")),
    path("", include("payroll.urls", namespace="payroll")),
    path("api/", include("api.urls", namespace="api")),
    path("oauth/", include("social_django.urls", namespace="social")),
    # path(
    #     "__reload__/",
    #     include("django_browser_reload.urls"),
    # ),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
