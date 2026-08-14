"""Seed the published PayNest pricing tiers.

Benchmarked against the August 2026 competitive research: entry/growth per-
user tiers sit at parity with HRPayHub's Bronze (N499) / Silver (N999) per
user/month, and the annual price is the 10%-discounted monthly equivalent.
Free tier caps at 3 employees; Enterprise is custom (no published price).

Edit prices in the Django admin (Marketing -> Pricing plans) as the model
moves; this migration only guarantees the first published state.
"""

from django.db import migrations

PLANS = [
    {
        "slug": "free",
        "name": "Free",
        "tagline": "Compliant payroll for teams starting out.",
        "monthly_price": "0",
        "annual_monthly_price": "0",
        "billing_note": "forever, up to 3 employees",
        "max_employees": 3,
        "features": [
            "PAYE, pension and NHF computation on current statutory rates",
            "Payslips for every run",
            "Reform-ready rate tables (2026 NTA and pre-reform PITA)",
            "Up to 3 employees",
            "Email support",
        ],
        "highlight": False,
        "sort_order": 0,
    },
    {
        "slug": "starter",
        "name": "Starter",
        "tagline": "The statutory payroll core for small teams.",
        "monthly_price": "499",
        "annual_monthly_price": "449",
        "billing_note": "per employee / month",
        "max_employees": 25,
        "features": [
            "Everything in Free, up to 25 employees",
            "Payroll runs and bank-ready payment files",
            "NHIS/NHIA, NSITF and ITF contribution engines",
            "Compliance calendar with due dates and overdue flags",
            "Leave and employee records",
            "Excel report exports (bank, PAYE, pension, NHF)",
        ],
        "highlight": False,
        "sort_order": 1,
    },
    {
        "slug": "growth",
        "name": "Growth",
        "tagline": "Finance-grade controls for scaling payroll.",
        "monthly_price": "999",
        "annual_monthly_price": "899",
        "billing_note": "per employee / month",
        "max_employees": None,
        "features": [
            "Everything in Starter, unlimited employees",
            "Cost-of-employment and finance reports",
            "Approvals and segregation of duties",
            "Audit trails and sensitive-access logs",
            "API access",
            "Priority support",
        ],
        "highlight": True,
        "sort_order": 2,
    },
    {
        "slug": "enterprise",
        "name": "Enterprise",
        "tagline": "Multi-company payroll with a dedicated team.",
        "monthly_price": None,
        "annual_monthly_price": None,
        "billing_note": "custom quote",
        "max_employees": None,
        "features": [
            "Everything in Growth",
            "Multi-company management",
            "Dedicated onboarding and migration",
            "Custom modules and SLA",
        ],
        "highlight": False,
        "sort_order": 3,
    },
]


def seed_pricing_plans(apps, schema_editor):
    PricingPlan = apps.get_model("marketing", "PricingPlan")
    for plan in PLANS:
        PricingPlan.objects.update_or_create(
            slug=plan["slug"],
            defaults={key: value for key, value in plan.items() if key != "slug"},
        )


def unseed_pricing_plans(apps, schema_editor):
    PricingPlan = apps.get_model("marketing", "PricingPlan")
    PricingPlan.objects.filter(slug__in=[plan["slug"] for plan in PLANS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("marketing", "0005_pricingplan"),
    ]

    operations = [
        migrations.RunPython(seed_pricing_plans, unseed_pricing_plans),
    ]
