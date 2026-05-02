from decimal import Decimal

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("payroll", "0039_companypayrollsetting_leave_allowance_percentage"),
    ]

    operations = [
        migrations.AddField(
            model_name="companypayrollsetting",
            name="pays_thirteenth_month",
            field=models.BooleanField(
                default=True,
                help_text="When enabled, employees receive 13th month in December.",
            ),
        ),
        migrations.AddField(
            model_name="companypayrollsetting",
            name="thirteenth_month_percentage",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("20.00"),
                help_text="Percentage of annual basic salary paid as 13th month.",
                max_digits=5,
                validators=[
                    django.core.validators.MinValueValidator(Decimal("0")),
                    django.core.validators.MaxValueValidator(Decimal("100")),
                ],
            ),
        ),
    ]
