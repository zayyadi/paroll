"""Seed competitor-tracking rows from the August 2026 market research.

Sources are the competitive-landscape research (Punch comparison, iSmartRecruit
Africa guide, vendor sites) verified as of 2026-08-14. Feature values that the
research could not confirm are left as "unknown" rather than guessed; update
rows in the Django admin as the market moves.
"""

from datetime import date
from django.db import migrations

AS_OF = date(2026, 8, 14)

VENDORS = [
    {
        "name": "HRPayHub",
        "website": "https://hrpayhub.com",
        "segment": "local",
        "status": "active",
        "pricing_summary": (
            "Bronze \u20a6499 \u2192 Silver \u20a6999 \u2192 top tier \u20a61,999 per "
            "user/month (annual billing); ~20% uplift for monthly; minimum 5 "
            "users. Transparent per-user \u20a6 pricing - the value anchor in the "
            "Punch comparison."
        ),
        "pricing_as_of": AS_OF,
        "features": {
            "statutory_paye": "yes",
            "statutory_reports": "yes",
            "compliance_calendar": "unknown",
            "audit_trails": "unknown",
            "segregation": "unknown",
            "bank_files": "unknown",
            "remita": "unknown",
            "ewa": "unknown",
            "mobile": "unknown",
            "published_pricing": "yes",
            "multi_country": "no",
            "eor": "no",
        },
        "positioning_notes": (
            "Transparent-pricing SMB analog; bundles accounting. If PayNest "
            "publishes \u20a6 tiers at parity, the comparison table favors PayNest's "
            "compliance depth (calendar, penalty flags, governance)."
        ),
        "source_url": "https://punchng.com/top-5-hr-payroll-software-in-nigeria/",
        "last_verified": AS_OF,
    },
    {
        "name": "SeamlessHR",
        "website": "https://seamlesshr.com",
        "segment": "local",
        "status": "active",
        "pricing_summary": "Quote-based enterprise suites; payroll financing offered.",
        "pricing_as_of": AS_OF,
        "features": {
            "statutory_paye": "yes",
            "statutory_reports": "yes",
            "compliance_calendar": "unknown",
            "audit_trails": "yes",
            "segregation": "unknown",
            "bank_files": "yes",
            "remita": "unknown",
            "ewa": "partial",
            "mobile": "yes",
            "published_pricing": "no",
            "multi_country": "no",
            "eor": "no",
        },
        "positioning_notes": (
            "Enterprise incumbent - quote-based and, per the Punch comparison, "
            "significantly more expensive than transparent per-user rivals. "
            "PayNest attacks on published pricing + compliance outputs."
        ),
        "source_url": "https://www.ismartrecruit.com/blog-top-hr-and-payroll-software-africa",
        "last_verified": AS_OF,
    },
    {
        "name": "Workpay",
        "website": "https://workpay.africa",
        "segment": "pan_african",
        "status": "active",
        "pricing_summary": "Quote/custom packages; freemium entry tier; USD-priced.",
        "pricing_as_of": AS_OF,
        "features": {
            "statutory_paye": "yes",
            "statutory_reports": "yes",
            "compliance_calendar": "unknown",
            "audit_trails": "unknown",
            "segregation": "unknown",
            "bank_files": "yes",
            "remita": "unknown",
            "ewa": "unknown",
            "mobile": "yes",
            "published_pricing": "no",
            "multi_country": "partial",
            "eor": "partial",
        },
        "positioning_notes": (
            "Pan-African SME/remote-team play, mobile-first, instant salary "
            "disbursements. Its multi-country/EOR breadth is PayNest's "
            "deliberate non-goal; Nigeria-first compliance depth is the answer."
        ),
        "source_url": "https://www.ismartrecruit.com/blog-top-hr-and-payroll-software-africa",
        "last_verified": AS_OF,
    },
    {
        "name": "HumanManager",
        "website": "",
        "segment": "local",
        "status": "active",
        "pricing_summary": "Custom quotes; Remita-linked payroll.",
        "pricing_as_of": AS_OF,
        "features": {
            "statutory_paye": "yes",
            "statutory_reports": "yes",
            "compliance_calendar": "unknown",
            "audit_trails": "unknown",
            "segregation": "unknown",
            "bank_files": "yes",
            "remita": "yes",
            "ewa": "unknown",
            "mobile": "unknown",
            "published_pricing": "no",
            "multi_country": "no",
            "eor": "no",
        },
        "positioning_notes": (
            "Sells the Remita link as a feature. PayNest's answer is to own "
            "the disbursement rail itself (roadmap 1.2) rather than resell it."
        ),
        "source_url": "",
        "last_verified": AS_OF,
    },
    {
        "name": "Bento Africa",
        "website": "",
        "segment": "local",
        "status": "defunct",
        "pricing_summary": (
            "Former flat tiers: $29 (Team, \u226410 cards) / $69 (Pro, \u226425) / "
            "$149 (Enterprise, 25+). Collapsed in 2025 amid failure to remit "
            "tax and pension contributions."
        ),
        "pricing_as_of": AS_OF,
        "features": {
            "statutory_paye": "yes",
            "statutory_reports": "partial",
            "compliance_calendar": "no",
            "audit_trails": "unknown",
            "segregation": "unknown",
            "bank_files": "yes",
            "remita": "no",
            "ewa": "unknown",
            "mobile": "yes",
            "published_pricing": "yes",
            "multi_country": "no",
            "eor": "no",
        },
        "positioning_notes": (
            "The trust-collapse cautionary tale. Its failure to remit is the "
            "category's open wound - exactly what PayNest's remittance "
            "oversight and audit trails answer."
        ),
        "source_url": "https://www.ismartrecruit.com/blog-top-hr-and-payroll-software-africa",
        "last_verified": AS_OF,
    },
    {
        "name": "PaidHR",
        "website": "https://www.paidhr.com",
        "segment": "ewa",
        "status": "active",
        "pricing_summary": "Not published; EWA at the core (claims $18M+/49 currencies processed).",
        "pricing_as_of": AS_OF,
        "features": {
            "statutory_paye": "yes",
            "statutory_reports": "yes",
            "compliance_calendar": "unknown",
            "audit_trails": "unknown",
            "segregation": "unknown",
            "bank_files": "yes",
            "remita": "unknown",
            "ewa": "yes",
            "mobile": "yes",
            "published_pricing": "unknown",
            "multi_country": "partial",
            "eor": "no",
        },
        "positioning_notes": "EWA-first competitor; the benchmark for roadmap items 1.3/2.2.",
        "source_url": "https://www.paidhr.com/blog/best-payroll-processing-systems",
        "last_verified": AS_OF,
    },
    {
        "name": "Earnipay",
        "website": "",
        "segment": "ewa",
        "status": "active",
        "pricing_summary": "EWA fintech; per-withdrawal fee model (not published in research).",
        "pricing_as_of": AS_OF,
        "features": {
            "statutory_paye": "no",
            "statutory_reports": "no",
            "compliance_calendar": "no",
            "audit_trails": "no",
            "segregation": "no",
            "bank_files": "no",
            "remita": "unknown",
            "ewa": "yes",
            "mobile": "yes",
            "published_pricing": "unknown",
            "multi_country": "no",
            "eor": "no",
        },
        "positioning_notes": "Nigeria's dedicated EWA fintech - partner candidate or proof point for EWA demand.",
        "source_url": "",
        "last_verified": AS_OF,
    },
    {
        "name": "Endeavour (Paymaster)",
        "website": "https://endeavournigeria.com",
        "segment": "local",
        "status": "active",
        "pricing_summary": "$30/month up to 10 employees + $1/employee/month beyond (total invoice).",
        "pricing_as_of": AS_OF,
        "features": {
            "statutory_paye": "yes",
            "statutory_reports": "yes",
            "compliance_calendar": "unknown",
            "audit_trails": "unknown",
            "segregation": "unknown",
            "bank_files": "unknown",
            "remita": "unknown",
            "ewa": "no",
            "mobile": "unknown",
            "published_pricing": "yes",
            "multi_country": "partial",
            "eor": "no",
        },
        "positioning_notes": (
            "Base + per-employee blended model; cheaper per seat at scale than "
            "per-user pricing - the reason PayNest's design needs a seat "
            "discount ladder at 100+ employees."
        ),
        "source_url": "https://www.ismartrecruit.com/blog-top-hr-and-payroll-software-africa",
        "last_verified": AS_OF,
    },
    {
        "name": "PaySpace",
        "website": "",
        "segment": "pan_african",
        "status": "active",
        "pricing_summary": "Contact vendor (Lite/Premier/Master/Outsourcing); multi-country tax engine.",
        "pricing_as_of": AS_OF,
        "features": {
            "statutory_paye": "yes",
            "statutory_reports": "yes",
            "compliance_calendar": "unknown",
            "audit_trails": "unknown",
            "segregation": "unknown",
            "bank_files": "yes",
            "remita": "no",
            "ewa": "unknown",
            "mobile": "yes",
            "published_pricing": "no",
            "multi_country": "yes",
            "eor": "no",
        },
        "positioning_notes": "43-country statutory engine - the multi-country benchmark PayNest deliberately does not chase.",
        "source_url": "https://www.ismartrecruit.com/blog-top-hr-and-payroll-software-africa",
        "last_verified": AS_OF,
    },
    {
        "name": "Deel",
        "website": "https://www.deel.com",
        "segment": "eor",
        "status": "active",
        "pricing_summary": "EOR ~$599/employee/month; global payroll and contractor platform.",
        "pricing_as_of": AS_OF,
        "features": {
            "statutory_paye": "no",
            "statutory_reports": "partial",
            "compliance_calendar": "unknown",
            "audit_trails": "unknown",
            "segregation": "unknown",
            "bank_files": "yes",
            "remita": "no",
            "ewa": "yes",
            "mobile": "yes",
            "published_pricing": "partial",
            "multi_country": "yes",
            "eor": "yes",
        },
        "positioning_notes": "Global EOR reference point; different business (employment law, not Nigerian statutory payroll).",
        "source_url": "https://nativeteams.com",
        "last_verified": AS_OF,
    },
]


def seed_competitors(apps, schema_editor):
    Competitor = apps.get_model("marketing", "Competitor")
    for vendor in VENDORS:
        Competitor.objects.update_or_create(
            name=vendor["name"],
            defaults={
                key: value for key, value in vendor.items() if key != "name"
            },
        )


def unseed_competitors(apps, schema_editor):
    Competitor = apps.get_model("marketing", "Competitor")
    Competitor.objects.filter(name__in=[v["name"] for v in VENDORS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("marketing", "0003_competitor"),
    ]

    operations = [
        migrations.RunPython(seed_competitors, unseed_competitors),
    ]
