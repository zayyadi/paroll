from decimal import Decimal

from django.db import migrations

# Personal Income Tax Act bands as amended by the Finance Acts (pre-NTA),
# effective 2021-2025. Tuples are [upper_threshold_or_null, rate_percent].
PITA_BANDS = [
    [300000, 7],
    [600000, 11],
    [1100000, 15],
    [1600000, 19],
    [3200000, 21],
    [None, 24],
]

# Nigeria Tax Act 2025 (effective 1 January 2026).
NTA_2025_BANDS = [
    [800000, 0],
    [3000000, 15],
    [12000000, 18],
    [25000000, 21],
    [50000000, 23],
    [None, 25],
]

VERSIONS = [
    {
        "name": "Personal Income Tax Act (pre-Nigeria Tax Act)",
        "effective_date": "2021-01-01",
        "paye_bands": PITA_BANDS,
        "minimum_wage_monthly": Decimal("30000.00"),
        "pension_employee_percentage": Decimal("8.00"),
        "pension_employer_percentage": Decimal("10.00"),
        "nhf_percentage": Decimal("2.50"),
    },
    {
        "name": "Personal Income Tax Act (NGN 70,000 minimum wage)",
        "effective_date": "2024-07-29",
        "paye_bands": PITA_BANDS,
        "minimum_wage_monthly": Decimal("70000.00"),
        "pension_employee_percentage": Decimal("8.00"),
        "pension_employer_percentage": Decimal("10.00"),
        "nhf_percentage": Decimal("2.50"),
    },
    {
        "name": "Nigeria Tax Act 2025",
        "effective_date": "2026-01-01",
        "paye_bands": NTA_2025_BANDS,
        "minimum_wage_monthly": Decimal("70000.00"),
        "pension_employee_percentage": Decimal("8.00"),
        "pension_employer_percentage": Decimal("10.00"),
        "nhf_percentage": Decimal("2.50"),
    },
]


def seed_statutory_rate_versions(apps, schema_editor):
    StatutoryRateVersion = apps.get_model("payroll", "StatutoryRateVersion")
    for version in VERSIONS:
        StatutoryRateVersion.objects.update_or_create(
            effective_date=version["effective_date"],
            defaults={
                "name": version["name"],
                "paye_bands": version["paye_bands"],
                "minimum_wage_monthly": version["minimum_wage_monthly"],
                "pension_employee_percentage": version["pension_employee_percentage"],
                "pension_employer_percentage": version["pension_employer_percentage"],
                "nhf_percentage": version["nhf_percentage"],
            },
        )


def unseed_statutory_rate_versions(apps, schema_editor):
    StatutoryRateVersion = apps.get_model("payroll", "StatutoryRateVersion")
    StatutoryRateVersion.objects.filter(
        effective_date__in=[v["effective_date"] for v in VERSIONS]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("payroll", "0060_statutoryrateversion"),
    ]

    operations = [
        migrations.RunPython(
            seed_statutory_rate_versions,
            reverse_code=unseed_statutory_rate_versions,
        ),
    ]
