# Generated for payroll lifecycle (Draft → Calculated → Reviewed → Approved → Locked → Paid) on 2026-09-04

from django.db import migrations, models


def backfill_status_from_closed(apps, schema_editor):
    PayrollRun = apps.get_model("payroll", "PayrollRun")
    # Bypass managers: at this point in history `all_objects` does not exist
    # yet and `objects` is PayManager (filters is_active=True), which would
    # silently skip inactive closed runs. `WHERE closed` is valid on both
    # SQLite (0/1) and Postgres (boolean).
    table = PayrollRun._meta.db_table
    schema_editor.execute(f'UPDATE "{table}" SET status = \'locked\' WHERE closed')


def reverse_backfill(apps, schema_editor):
    # Reverse keeps status but clears derived closed where status is draft-like.
    # Intentionally a no-op for locked rows to avoid data loss.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("payroll", "0069_audittrail_company"),
    ]

    operations = [
        migrations.AddField(
            model_name="payrollrun",
            name="status",
            field=models.CharField(
                choices=[
                    ("draft", "Draft"),
                    ("calculated", "Calculated"),
                    ("reviewed", "Reviewed"),
                    ("approved", "Approved"),
                    ("locked", "Locked"),
                    ("paid", "Paid"),
                ],
                db_index=True,
                default="draft",
                help_text="Payroll lifecycle: Draft → Calculated → Reviewed → Approved → Locked → Paid.",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="payrollrun",
            name="closed",
            field=models.BooleanField(
                default=False,
                help_text="Legacy lock flag. Derived from status (LOCKED/PAID). Use status transitions instead.",
            ),
        ),
        migrations.RunPython(backfill_status_from_closed, reverse_backfill),
    ]
