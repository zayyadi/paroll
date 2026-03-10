from django.urls import path

from marketing import views

app_name = "marketing"

urlpatterns = [
    path("", views.landing, name="landing"),
    path("pricing/", views.pricing, name="pricing"),
    path("about/", views.about, name="about"),
    path("support/", views.support, name="support"),
    path("security/", views.security, name="security"),
    path("contact/", views.contact, name="contact"),
    path("legal/privacy/", views.privacy, name="privacy"),
    path("legal/terms/", views.terms, name="terms"),
    path("legal/cookies/", views.cookies, name="cookies"),
]
