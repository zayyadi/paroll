# Generated for Phase-0 A2 tenant isolation hardening on 2026-09-04

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("company", "0001_initial"),
        ("payroll", "0068_companypayrollsetting_ewa_advance_percent_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="audittrail",
            name="company",
            field=models.ForeignKey(
                blank=True,
                db_index=True,
                help_text="Tenant owner. Required for new rows; NULL marks legacy rows pending backfill.",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="payroll_audit_trails",
                to="company.company",
            ),
        ),
    ]
