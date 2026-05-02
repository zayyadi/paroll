# Generated migration to fix LeaveBalance unique constraint issue

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("payroll", "0024_publicholiday_remove_leaverequest_available_days_and_more"),
    ]

    operations = [
        # First, remove the unique constraint on employee_id alone
        migrations.AlterField(
            model_name="leavebalance",
            name="employee",
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="leave_balance",
                to="payroll.employeeprofile",
            ),
        ),
        # Ensure the composite unique constraint on employee_id and year exists
        migrations.AlterUniqueTogether(
            name="leavebalance",
            unique_together={("employee", "year")},
        ),
    ]
