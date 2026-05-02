# Generated manually for disciplinary workflow models.

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounting", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="DisciplinaryCase",
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
                ("created_at", models.DateTimeField(auto_now_add=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True, null=True)),
                ("case_number", models.CharField(editable=False, max_length=30, unique=True)),
                ("allegation_summary", models.CharField(max_length=255)),
                ("allegation_details", models.TextField()),
                ("incident_date", models.DateField(blank=True, null=True)),
                ("reported_at", models.DateTimeField(default=django.utils.timezone.now)),
                (
                    "violation_level",
                    models.CharField(
                        choices=[
                            ("LEVEL_1", "Level 1 - Minor"),
                            ("LEVEL_2", "Level 2 - Moderate"),
                            ("LEVEL_3", "Level 3 - Serious"),
                            ("LEVEL_4", "Level 4 - Major"),
                            ("LEVEL_5", "Level 5 - Critical"),
                        ],
                        default="LEVEL_1",
                        max_length=20,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("INTAKE", "Intake"),
                            ("UNDER_INVESTIGATION", "Under Investigation"),
                            ("PANEL_REVIEW", "Panel Review"),
                            ("DECIDED", "Decided"),
                            ("APPEALED", "Appealed"),
                            ("CLOSED", "Closed"),
                            ("DISMISSED", "Dismissed"),
                        ],
                        default="INTAKE",
                        max_length=30,
                    ),
                ),
                (
                    "finding",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("UNSUBSTANTIATED", "Unsubstantiated"),
                            ("PARTIALLY_SUBSTANTIATED", "Partially Substantiated"),
                            ("SUBSTANTIATED", "Substantiated"),
                        ],
                        max_length=30,
                        null=True,
                    ),
                ),
                (
                    "required_review_level",
                    models.CharField(
                        choices=[
                            ("MANAGER", "Manager Review"),
                            ("HR_LEAD", "HR + Functional Lead"),
                            ("PANEL", "Disciplinary Panel"),
                            ("EXECUTIVE", "Executive Oversight"),
                        ],
                        default="MANAGER",
                        max_length=20,
                    ),
                ),
                ("emergency_case", models.BooleanField(default=False)),
                ("repeat_offense_suspected", models.BooleanField(default=False)),
                ("power_imbalance_flag", models.BooleanField(default=False)),
                ("conflict_of_interest_flag", models.BooleanField(default=False)),
                ("mental_health_context", models.BooleanField(default=False)),
                ("cultural_context", models.BooleanField(default=False)),
                ("interim_measures", models.TextField(blank=True)),
                ("findings_summary", models.TextField(blank=True)),
                ("decision_rationale", models.TextField(blank=True)),
                ("due_process_notified_at", models.DateTimeField(blank=True, null=True)),
                ("respondent_response_at", models.DateTimeField(blank=True, null=True)),
                ("decision_at", models.DateTimeField(blank=True, null=True)),
                ("appeal_window_ends_at", models.DateTimeField(blank=True, null=True)),
                ("closed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "decided_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="disciplinary_cases_decided",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "investigator",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="disciplinary_cases_investigated",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "reporter",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="disciplinary_cases_reported",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "respondent",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="disciplinary_cases_as_respondent",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Disciplinary Case",
                "verbose_name_plural": "Disciplinary Cases",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="DisciplinaryAppeal",
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
                ("created_at", models.DateTimeField(auto_now_add=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True, null=True)),
                (
                    "grounds",
                    models.CharField(
                        choices=[
                            ("PROCEDURAL_UNFAIRNESS", "Procedural Unfairness"),
                            ("NEW_EVIDENCE", "New Evidence"),
                            ("BIAS_OR_CONFLICT", "Bias or Conflict of Interest"),
                            ("DISPROPORTIONATE_SANCTION", "Disproportionate Sanction"),
                        ],
                        max_length=40,
                    ),
                ),
                ("details", models.TextField()),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("SUBMITTED", "Submitted"),
                            ("UNDER_REVIEW", "Under Review"),
                            ("UPHELD", "Upheld"),
                            ("MODIFIED", "Modified"),
                            ("OVERTURNED", "Overturned"),
                            ("REINVESTIGATION_ORDERED", "Reinvestigation Ordered"),
                            ("REJECTED", "Rejected"),
                        ],
                        default="SUBMITTED",
                        max_length=30,
                    ),
                ),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("outcome_notes", models.TextField(blank=True)),
                (
                    "appellant",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="disciplinary_appeals_filed",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "case",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="appeals",
                        to="accounting.disciplinarycase",
                    ),
                ),
                (
                    "reviewed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="disciplinary_appeals_reviewed",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Disciplinary Appeal",
                "verbose_name_plural": "Disciplinary Appeals",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="DisciplinaryEvidence",
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
                ("created_at", models.DateTimeField(auto_now_add=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True, null=True)),
                ("title", models.CharField(max_length=255)),
                (
                    "evidence_type",
                    models.CharField(
                        choices=[
                            ("DOCUMENT", "Document"),
                            ("EMAIL", "Email"),
                            ("CHAT", "Chat"),
                            ("SYSTEM_LOG", "System Log"),
                            ("CCTV", "CCTV"),
                            ("WITNESS_STATEMENT", "Witness Statement"),
                            ("OTHER", "Other"),
                        ],
                        max_length=30,
                    ),
                ),
                ("description", models.TextField(blank=True)),
                ("file", models.FileField(blank=True, null=True, upload_to="disciplinary/evidence/")),
                ("is_confidential", models.BooleanField(default=False)),
                ("chain_of_custody_notes", models.TextField(blank=True)),
                ("reliability_score", models.PositiveSmallIntegerField(blank=True, null=True)),
                (
                    "case",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="evidence_items",
                        to="accounting.disciplinarycase",
                    ),
                ),
                (
                    "submitted_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="disciplinary_evidence_submitted",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Disciplinary Evidence",
                "verbose_name_plural": "Disciplinary Evidence",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="DisciplinarySanction",
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
                ("created_at", models.DateTimeField(auto_now_add=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True, null=True)),
                (
                    "sanction_type",
                    models.CharField(
                        choices=[
                            ("COACHING", "Coaching"),
                            ("WRITTEN_WARNING", "Written Warning"),
                            ("FINAL_WARNING", "Final Warning"),
                            ("TRAINING", "Mandatory Training"),
                            ("PERFORMANCE_PLAN", "Performance Improvement Plan"),
                            ("ROLE_RESTRICTION", "Role Restriction"),
                            ("SUSPENSION", "Suspension"),
                            ("DEMOTION", "Demotion"),
                            ("TERMINATION_REVIEW", "Termination Review"),
                            ("TERMINATION", "Termination"),
                        ],
                        max_length=30,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("ACTIVE", "Active"),
                            ("COMPLETED", "Completed"),
                            ("REVOKED", "Revoked"),
                        ],
                        default="ACTIVE",
                        max_length=15,
                    ),
                ),
                ("rationale", models.TextField()),
                ("effective_date", models.DateField(default=django.utils.timezone.now)),
                ("duration_days", models.PositiveIntegerField(blank=True, null=True)),
                ("compliance_due_date", models.DateField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("is_rehabilitative", models.BooleanField(default=True)),
                (
                    "case",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sanctions",
                        to="accounting.disciplinarycase",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="disciplinary_sanctions_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Disciplinary Sanction",
                "verbose_name_plural": "Disciplinary Sanctions",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="disciplinarycase",
            index=models.Index(fields=["case_number"], name="acct_disc_case_idx"),
        ),
        migrations.AddIndex(
            model_name="disciplinarycase",
            index=models.Index(fields=["status"], name="acct_disc_status_idx"),
        ),
        migrations.AddIndex(
            model_name="disciplinarycase",
            index=models.Index(fields=["violation_level"], name="acct_disc_level_idx"),
        ),
        migrations.AddIndex(
            model_name="disciplinarycase",
            index=models.Index(fields=["required_review_level"], name="acct_disc_review_idx"),
        ),
    ]
