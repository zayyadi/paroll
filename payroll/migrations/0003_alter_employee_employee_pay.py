# Generated by Django 4.0.2 on 2022-10-08 19:50

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('payroll', '0002_alter_employee_date_of_birth_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='employee',
            name='employee_pay',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='employee_pay', to='payroll.payroll'),
        ),
    ]
