# Generated by Django 4.0.2 on 2022-10-20 13:36

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('payroll', '0015_employeeprofile_net_pay'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='variablecalc',
            name='basic_salary',
        ),
    ]
