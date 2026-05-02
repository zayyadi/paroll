from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("payroll", "0036_tenantize_leave_policy_and_holiday"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="payroll",
            name="rent_relief",
        ),
    ]
