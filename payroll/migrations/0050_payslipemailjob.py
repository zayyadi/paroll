from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("payroll", "0049_company_chat_phase2"),
    ]

    operations = [
        migrations.CreateModel(
            name="PayslipEmailJob",
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
                    "status",
                    models.CharField(
                        choices=[
                            ("queued", "Queued"),
                            ("running", "Running"),
                            ("sent", "Sent"),
                            ("partial", "Partial"),
                            ("failed", "Failed"),
                        ],
                        db_index=True,
                        default="queued",
                        max_length=20,
                    ),
                ),
                ("celery_task_id", models.CharField(blank=True, max_length=255)),
                ("sent_count", models.PositiveIntegerField(default=0)),
                ("skipped_count", models.PositiveIntegerField(default=0)),
                ("skipped_details", models.JSONField(blank=True, default=list)),
                ("error_message", models.TextField(blank=True)),
                ("queued_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "payroll_run",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="payslip_email_jobs",
                        to="payroll.payrollrun",
                    ),
                ),
            ],
            options={
                "ordering": ("-queued_at",),
                "indexes": [
                    models.Index(fields=["status", "queued_at"], name="payroll_pay_status_20d3c5_idx"),
                    models.Index(fields=["payroll_run", "status"], name="payroll_pay_payroll_b08f1b_idx"),
                ],
            },
        ),
    ]
