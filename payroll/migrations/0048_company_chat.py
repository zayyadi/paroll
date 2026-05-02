from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [
        ("payroll", "0047_surveyquestion_assetcategory_benefitplan_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="CompanyChatRoom",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("slug", models.SlugField(max_length=64)),
                ("name", models.CharField(default="Company Chat", max_length=120)),
                ("description", models.TextField(blank=True)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="chat_rooms",
                        to="company.company",
                    ),
                ),
            ],
            options={
                "ordering": ["name"],
                "indexes": [models.Index(fields=["company", "is_active"], name="payroll_com_company_69040d_idx")],
                "constraints": [
                    models.UniqueConstraint(fields=("company", "slug"), name="uniq_company_chat_room_slug")
                ],
            },
        ),
        migrations.CreateModel(
            name="CompanyChatMessage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("body", models.TextField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "room",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="messages",
                        to="payroll.companychatroom",
                    ),
                ),
                (
                    "sender",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="chat_messages",
                        to="payroll.employeeprofile",
                    ),
                ),
            ],
            options={
                "ordering": ["created_at", "id"],
                "indexes": [models.Index(fields=["room", "created_at"], name="payroll_com_room_id_00d25a_idx")],
            },
        ),
        migrations.CreateModel(
            name="CompanyChatReadState",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("last_read_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "employee",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="chat_read_states",
                        to="payroll.employeeprofile",
                    ),
                ),
                (
                    "last_read_message",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="payroll.companychatmessage",
                    ),
                ),
                (
                    "room",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="read_states",
                        to="payroll.companychatroom",
                    ),
                ),
            ],
            options={
                "indexes": [models.Index(fields=["room", "employee"], name="payroll_com_room_id_117e4e_idx")],
                "constraints": [
                    models.UniqueConstraint(fields=("room", "employee"), name="uniq_company_chat_read_state")
                ],
            },
        ),
    ]
