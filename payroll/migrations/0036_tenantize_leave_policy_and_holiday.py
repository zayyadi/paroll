import django.db.models.deletion
from django.db import migrations, models


def backfill_tenant_for_leave_models(apps, schema_editor):
    Company = apps.get_model("company", "Company")
    PublicHoliday = apps.get_model("payroll", "PublicHoliday")
    LeavePolicy = apps.get_model("payroll", "LeavePolicy")

    default_company, _ = Company.objects.get_or_create(
        name="Default Company",
        defaults={"slug": "default-company"},
    )

    PublicHoliday.objects.filter(company__isnull=True).update(company=default_company)
    LeavePolicy.objects.filter(company__isnull=True).update(company=default_company)


class Migration(migrations.Migration):

    dependencies = [
        ("company", "0003_backfill_memberships"),
        ("payroll", "0035_multitenancy_company_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="leavepolicy",
            name="company",
            field=models.ForeignKey(
                blank=True,
                db_index=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="leave_policies",
                to="company.company",
            ),
        ),
        migrations.AddField(
            model_name="publicholiday",
            name="company",
            field=models.ForeignKey(
                blank=True,
                db_index=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="public_holidays",
                to="company.company",
            ),
        ),
        migrations.AlterField(
            model_name="leavepolicy",
            name="leave_type",
            field=models.CharField(
                choices=[
                    ("CASUAL", "Casual Leave"),
                    ("SICK", "Sick Leave"),
                    ("ANNUAL", "Annual Leave"),
                    ("MATERNITY", "Maternity Leave"),
                    ("PATERNITY", "Paternity Leave"),
                ],
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="publicholiday",
            name="date",
            field=models.DateField(),
        ),
        migrations.RunPython(
            backfill_tenant_for_leave_models,
            migrations.RunPython.noop,
        ),
        migrations.AlterUniqueTogether(
            name="leavepolicy",
            unique_together={("company", "leave_type")},
        ),
        migrations.AlterUniqueTogether(
            name="publicholiday",
            unique_together={("company", "date")},
        ),
    ]
