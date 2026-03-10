from django.contrib import messages
from django.shortcuts import redirect, render

from marketing.forms import LeadInquiryForm
from marketing.models import MarketingEvent


def _track_event(request, event_name, metadata=None):
    session_key = ""
    if getattr(request, "session", None):
        session_key = request.session.session_key or ""
    user = request.user if request.user.is_authenticated else None
    MarketingEvent.objects.create(
        event_name=event_name,
        path=request.path,
        user=user,
        session_key=session_key,
        metadata=metadata or {},
    )


def landing(request):
    _track_event(request, "marketing.page_view", {"page": "landing"})
    return render(request, "marketing/landing.html")


def pricing(request):
    _track_event(request, "marketing.page_view", {"page": "pricing"})
    return render(request, "marketing/pricing.html")


def about(request):
    _track_event(request, "marketing.page_view", {"page": "about"})
    return render(request, "marketing/about.html")


def support(request):
    _track_event(request, "marketing.page_view", {"page": "support"})
    return render(request, "marketing/support.html")


def security(request):
    _track_event(request, "marketing.page_view", {"page": "security"})
    return render(request, "marketing/security.html")


def privacy(request):
    _track_event(request, "marketing.page_view", {"page": "privacy"})
    return render(request, "marketing/privacy.html")


def terms(request):
    _track_event(request, "marketing.page_view", {"page": "terms"})
    return render(request, "marketing/terms.html")


def cookies(request):
    _track_event(request, "marketing.page_view", {"page": "cookies"})
    return render(request, "marketing/cookies.html")


def contact(request):
    form = LeadInquiryForm(request.POST or None)
    if request.method == "GET":
        _track_event(request, "marketing.page_view", {"page": "contact"})

    if request.method == "POST" and form.is_valid():
        form.save()
        _track_event(request, "marketing.contact_submitted")
        messages.success(request, "Thanks. Our team will contact you shortly.")
        return redirect("marketing:contact")

    return render(request, "marketing/contact.html", {"form": form})
