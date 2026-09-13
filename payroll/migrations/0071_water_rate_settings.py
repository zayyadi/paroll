# Generated for governed water-rate deduction (E3) on 2026-09-04

from decimal import Decimal
import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("payroll", "0070_payrollrun_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="companypayrollsetting",
            name="water_rate_high",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("200.00"),
                help_text="Monthly water-rate deduction when basic salary is above threshold.",
                max_digits=12,
                validators=[django.core.validators.MinValueValidator(Decimal("0"))],
            ),
        ),
        migrations.AddField(
            model_name="companypayrollsetting",
            name="water_rate_low",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("150.00"),
                help_text="Monthly water-rate deduction when basic salary is at/below threshold.",
                max_digits=12,
                validators=[django.core.validators.MinValueValidator(Decimal("0"))],
            ),
        ),
        migrations.AddField(
            model_name="companypayrollsetting",
            name="water_rate_threshold",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("75000.00"),
                help_text="Basic-salary threshold governing the water-rate deduction. At or below this, water_rate_low applies; above it, water_rate_high.",
                max_digits=12,
            ),
        ),
    ]
