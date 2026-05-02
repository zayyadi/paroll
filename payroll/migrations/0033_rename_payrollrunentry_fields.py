from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("payroll", "0032_rename_pay_models"),
    ]

    operations = [
        migrations.RenameField(
            model_name="payrollrunentry",
            old_name="paydays_id",
            new_name="payroll_run",
        ),
        migrations.RenameField(
            model_name="payrollrunentry",
            old_name="payroll_id",
            new_name="payroll_entry",
        ),
    ]
