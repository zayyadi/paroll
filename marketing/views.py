from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render
from django.utils import timezone

from marketing.forms import LeadInquiryForm
from marketing.models import (
    Competitor,
    FEATURE_CATALOG,
    MarketingEvent,
    PricingPlan,
)


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


def _is_super_admin(user) -> bool:
    return user.is_superuser or user.groups.filter(name="Super Admin").exists()


@login_required
def competitor_tracking(request):
    """
    Internal market-intelligence page: capability gap matrix and per-vendor
    pricing/status records, kept current from the Django admin so positioning
    never depends on a quarterly re-research.
    """
    if not _is_super_admin(request.user):
        return HttpResponseForbidden(
            "Only super admins can view competitor tracking."
        )

    as_of = timezone.localdate()
    competitors = list(Competitor.objects.all())

    matrix = []
    for key, label, paynest in FEATURE_CATALOG:
        # Cells are a list aligned with ``competitors`` so the template can
        # index them with the existing ``index`` template filter.
        row = {
            "key": key,
            "label": label,
            "paynest": paynest,
            "cells": [competitor.feature_status(key) for competitor in competitors],
        }
        matrix.append(row)

    for competitor in competitors:
        competitor.is_stale_flag = competitor.is_stale(as_of)
        competitor.their_lead = sum(
            1
            for key, _, paynest in FEATURE_CATALOG
            if competitor.feature_status(key) == "yes" and paynest != "yes"
        )
        competitor.our_lead = sum(
            1
            for key, _, paynest in FEATURE_CATALOG
            if competitor.feature_status(key) != "yes" and paynest == "yes"
        )

    stale_count = sum(1 for c in competitors if c.is_stale_flag)
    published_pricing_count = sum(
        1 for c in competitors if c.feature_status("published_pricing") == "yes"
    )
    defunct_count = sum(1 for c in competitors if c.status == Competitor.Status.DEFUNCT)

    return render(
        request,
        "marketing/competitor_tracking.html",
        {
            "competitors": competitors,
            "matrix": matrix,
            "feature_count": len(FEATURE_CATALOG),
            "stale_count": stale_count,
            "published_pricing_count": published_pricing_count,
            "defunct_count": defunct_count,
            "as_of": as_of,
        },
    )


def landing(request):
    _track_event(request, "marketing.page_view", {"page": "landing"})
    return render(request, "marketing/landing.html")


def pricing(request):
    _track_event(request, "marketing.page_view", {"page": "pricing"})
    return render(
        request,
        "marketing/pricing.html",
        {"plans": PricingPlan.objects.filter(is_active=True)},
    )


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
