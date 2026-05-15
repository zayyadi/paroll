from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("payroll", "0050_payslipemailjob"),
    ]

    operations = [
        migrations.AddField(
            model_name="allowance",
            name="source_leave_request",
            field=models.OneToOneField(
                blank=True,
                help_text="Leave request that generated this automatic leave allowance.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="processed_leave_allowance",
                to="payroll.leaverequest",
            ),
        ),
        migrations.CreateModel(
            name="LeaveAllowanceEmailJob",
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
                (
                    "amount",
                    models.DecimalField(decimal_places=2, max_digits=12),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("queued", "Queued"),
                            ("running", "Running"),
                            ("sent", "Sent"),
                            ("failed", "Failed"),
                        ],
                        db_index=True,
                        default="queued",
                        max_length=20,
                    ),
                ),
                ("celery_task_id", models.CharField(blank=True, max_length=255)),
                ("error_message", models.TextField(blank=True)),
                (
                    "queued_at",
                    models.DateTimeField(auto_now_add=True, db_index=True),
                ),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "allowance",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="leave_allowance_email_job",
                        to="payroll.allowance",
                    ),
                ),
                (
                    "leave_request",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="allowance_email_job",
                        to="payroll.leaverequest",
                    ),
                ),
            ],
            options={
                "ordering": ("-queued_at",),
            },
        ),
        migrations.AddIndex(
            model_name="leaveallowanceemailjob",
            index=models.Index(
                fields=["status", "queued_at"],
                name="payroll_lea_status_bc4f8c_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="leaveallowanceemailjob",
            index=models.Index(
                fields=["leave_request", "status"],
                name="payroll_lea_leave_r_f9490e_idx",
            ),
        ),
    ]
