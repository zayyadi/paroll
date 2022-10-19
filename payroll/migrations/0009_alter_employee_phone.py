# Generated by Django 4.0.2 on 2022-10-09 15:09

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('payroll', '0008_alter_employee_address_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='employee',
            name='phone',
            field=models.CharField(blank=True, default=1234567890, max_length=13, unique=True, validators=[django.core.validators.RegexValidator(message="Phone number must be entered in the format: '+999999999'. Up to 11 digits allowed.", regex='^\\+?1?\\d{3}\\d{9,11}$')], verbose_name='phone number'),
        ),
    ]
