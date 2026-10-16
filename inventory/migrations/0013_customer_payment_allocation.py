from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0012_order_line_tax_totals"),
    ]

    operations = [
        migrations.CreateModel(
            name="CustomerPaymentAllocation",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "amount",
                    models.DecimalField(decimal_places=2, max_digits=18),
                ),
                (
                    "allocation_date",
                    models.DateField(default=django.utils.timezone.now),
                ),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="customer_payment_allocations",
                        to="company.company",
                    ),
                ),
                (
                    "invoice",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="payment_allocations",
                        to="inventory.salesinvoice",
                    ),
                ),
                (
                    "payment",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="allocations",
                        to="inventory.customerpayment",
                    ),
                ),
            ],
            options={
                "ordering": ["allocation_date", "created_at", "id"],
            },
        ),
    ]
