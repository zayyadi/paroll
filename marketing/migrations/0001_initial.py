from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="LeadInquiry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("full_name", models.CharField(max_length=120)),
                ("work_email", models.EmailField(max_length=254)),
                ("company_name", models.CharField(max_length=150)),
                (
                    "company_size",
                    models.CharField(
                        choices=[
                            ("1-10", "1-10"),
                            ("11-50", "11-50"),
                            ("51-200", "51-200"),
                            ("201-500", "201-500"),
                            ("500+", "500+"),
                        ],
                        max_length=20,
                    ),
                ),
                ("message", models.TextField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
