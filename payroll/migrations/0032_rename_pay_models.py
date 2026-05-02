from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("payroll", "0031_remove_payroll_rent_paid_and_more"),
    ]

    operations = [
        migrations.RenameModel(old_name="PayVar", new_name="PayrollEntry"),
        migrations.RenameModel(old_name="PayT", new_name="PayrollRun"),
        migrations.RenameModel(old_name="Payday", new_name="PayrollRunEntry"),
    ]
