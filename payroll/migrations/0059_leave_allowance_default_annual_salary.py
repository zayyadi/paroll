from decimal import Decimal

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("payroll", "0058_bankpaymentfile_contracttemplate_employeetransfer_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="companypayrollsetting",
            name="leave_allowance_percentage",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("10.00"),
                help_text="Percentage of annual basic salary paid as leave allowance.",
                max_digits=5,
                validators=[
                    django.core.validators.MinValueValidator(Decimal("0")),
                    django.core.validators.MaxValueValidator(Decimal("100")),
                ],
            ),
        ),
    ]
