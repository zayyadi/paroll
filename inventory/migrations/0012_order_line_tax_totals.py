from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0011_alter_customer_credit_limit_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="purchaseorderline",
            name="vat_rate",
            field=models.DecimalField(
                decimal_places=4,
                default=Decimal("0.0000"),
                max_digits=7,
            ),
        ),
        migrations.AddField(
            model_name="purchaseorderline",
            name="vat_amount",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                max_digits=18,
            ),
        ),
        migrations.AddField(
            model_name="salesorderline",
            name="total_amount",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                max_digits=18,
            ),
        ),
        migrations.AddField(
            model_name="salesorderline",
            name="vat_rate",
            field=models.DecimalField(
                decimal_places=4,
                default=Decimal("0.0000"),
                max_digits=7,
            ),
        ),
        migrations.AddField(
            model_name="salesorderline",
            name="vat_amount",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                max_digits=18,
            ),
        ),
    ]
