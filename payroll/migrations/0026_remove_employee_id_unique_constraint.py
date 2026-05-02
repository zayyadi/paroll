from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("payroll", "0025_fix_leave_balance_unique_constraint"),
    ]

    def _drop_unique_constraint(apps, schema_editor):
        if schema_editor.connection.vendor != "postgresql":
            return
        schema_editor.execute(
            "ALTER TABLE payroll_leavebalance "
            "DROP CONSTRAINT IF EXISTS payroll_leavebalance_employee_id_key;"
        )

    def _restore_unique_constraint(apps, schema_editor):
        if schema_editor.connection.vendor != "postgresql":
            return
        schema_editor.execute(
            "ALTER TABLE payroll_leavebalance "
            "ADD CONSTRAINT payroll_leavebalance_employee_id_key UNIQUE (employee_id);"
        )

    operations = [
        migrations.RunPython(_drop_unique_constraint, _restore_unique_constraint),
    ]
