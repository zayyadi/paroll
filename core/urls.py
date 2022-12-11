from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static


urlpatterns = [
    path("admin/", admin.site.urls),
    path("account/", include("accounts.urls", namespace="accounts")),
    path("account/", include("django.contrib.auth.urls")),
    path("", include("payroll.urls", namespace="payroll")),
    path("oauth/", include("social_django.urls", namespace="social"))
    # path("employee", include("employee.urls", namespace="employee")),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
