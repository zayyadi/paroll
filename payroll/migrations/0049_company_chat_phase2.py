from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("payroll", "0048_company_chat"),
    ]

    operations = [
        migrations.AddField(
            model_name="companychatroom",
            name="room_type",
            field=models.CharField(
                choices=[("company", "Company"), ("team", "Team"), ("direct", "Direct")],
                default="company",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="companychatroom",
            name="created_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="created_chat_rooms",
                to="payroll.employeeprofile",
            ),
        ),
        migrations.CreateModel(
            name="CompanyChatRoomMember",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("role", models.CharField(choices=[("member", "Member"), ("admin", "Admin")], default="member", max_length=20)),
                ("is_active", models.BooleanField(default=True)),
                ("joined_at", models.DateTimeField(auto_now_add=True)),
                (
                    "employee",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="chat_memberships",
                        to="payroll.employeeprofile",
                    ),
                ),
                (
                    "room",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="memberships",
                        to="payroll.companychatroom",
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(fields=["room", "is_active"], name="payroll_com_room_id_8ec9d1_idx"),
                    models.Index(fields=["employee", "is_active"], name="payroll_com_employe_888e76_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(fields=("room", "employee"), name="uniq_company_chat_room_member")
                ],
            },
        ),
    ]
