"""Move the disciplinary models from accounting to payroll.

State only: the tables keep their accounting_* names (Meta.db_table), so no
rows move. The content types are renamed so permissions, group grants and
approval-request links follow the models, and stored approval policies that
name accounting.*_disciplinary* permissions are rewritten.
"""
import json
import re

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


MODELS = [
    "disciplinarycase",
    "disciplinarycaseaudit",
    "disciplinaryevidence",
    "disciplinarysanction",
    "disciplinaryappeal",
]


def _relabel(apps, old, new):
    ContentType = apps.get_model("contenttypes", "ContentType")
    for model in MODELS:
        if not ContentType.objects.filter(app_label=new, model=model).exists():
            ContentType.objects.filter(app_label=old, model=model).update(app_label=new)

    pattern = re.compile(rf"\b{old}\.(\w*disciplinary\w*)\b")

    def rewrite(value):
        text = json.dumps(value)
        updated = pattern.sub(rf"{new}.\1", text)
        return json.loads(updated) if updated != text else None

    ApprovalPolicy = apps.get_model("approvals", "ApprovalPolicy")
    for policy in ApprovalPolicy.objects.all():
        stages = rewrite(policy.stages)
        if stages is not None:
            ApprovalPolicy.objects.filter(pk=policy.pk).update(stages=stages)
    ApprovalRequest = apps.get_model("approvals", "ApprovalRequest")
    for request in ApprovalRequest.objects.all():
        snapshot = rewrite(request.policy_snapshot)
        if snapshot is not None:
            # queryset.update skips the audit-protection save() override.
            ApprovalRequest.objects.filter(pk=request.pk).update(policy_snapshot=snapshot)


def forwards(apps, schema_editor):
    _relabel(apps, "accounting", "payroll")


def backwards(apps, schema_editor):
    _relabel(apps, "payroll", "accounting")


class Migration(migrations.Migration):

    dependencies = [
        ("company", "0006_companymembership_groups"),
        ("payroll", "0094_recompute_payroll_figures"),
        ("accounting", "0021_workflow_base_managers"),
        ("approvals", "0002_alter_approvaldecision_options_and_more"),
        ("contenttypes", "0002_remove_content_type_name"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
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
                        ("case_number", models.CharField(editable=False, max_length=30)),
                        ("allegation_summary", models.CharField(max_length=255)),
                        ("allegation_details", models.TextField()),
                        ("incident_date", models.DateField(blank=True, null=True)),
                        (
                            "reported_at",
                            models.DateTimeField(default=django.utils.timezone.now),
                        ),
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
                        (
                            "due_process_notified_at",
                            models.DateTimeField(blank=True, null=True),
                        ),
                        ("respondent_response_at", models.DateTimeField(blank=True, null=True)),
                        ("decision_at", models.DateTimeField(blank=True, null=True)),
                        ("appeal_window_ends_at", models.DateTimeField(blank=True, null=True)),
                        ("closed_at", models.DateTimeField(blank=True, null=True)),
                        (
                            "company",
                            models.ForeignKey(
                                blank=True,
                                null=True,
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="disciplinary_cases",
                                to="company.company",
                            ),
                        ),
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
                        "db_table": "accounting_disciplinarycase",
                        "ordering": ["-created_at"],
                        "permissions": [
                            (
                                "review_hr_disciplinarycase",
                                "Can approve HR lead disciplinary decisions",
                            ),
                            (
                                "review_panel_disciplinarycase",
                                "Can approve panel disciplinary decisions",
                            ),
                            (
                                "review_executive_disciplinarycase",
                                "Can approve executive disciplinary decisions",
                            ),
                        ],
                        "base_manager_name": "objects",
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
                            "reviewed_by",
                            models.ForeignKey(
                                blank=True,
                                null=True,
                                on_delete=django.db.models.deletion.SET_NULL,
                                related_name="disciplinary_appeals_reviewed",
                                to=settings.AUTH_USER_MODEL,
                            ),
                        ),
                        (
                            "case",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="appeals",
                                to="payroll.disciplinarycase",
                            ),
                        ),
                    ],
                    options={
                        "verbose_name": "Disciplinary Appeal",
                        "verbose_name_plural": "Disciplinary Appeals",
                        "db_table": "accounting_disciplinaryappeal",
                        "ordering": ["-created_at"],
                        "base_manager_name": "objects",
                    },
                ),
                migrations.CreateModel(
                    name="DisciplinaryCaseAudit",
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
                            "action",
                            models.CharField(
                                choices=[
                                    ("created", "Created"),
                                    ("investigation_started", "Investigation Started"),
                                    ("decision_recorded", "Decision Recorded"),
                                    ("sanction_created", "Sanction Created"),
                                    ("sanction_completed", "Sanction Completed"),
                                    ("appeal_submitted", "Appeal Submitted"),
                                    ("appeal_reviewed", "Appeal Reviewed"),
                                    ("status_changed", "Status Changed"),
                                    ("case_closed", "Case Closed"),
                                ],
                                max_length=40,
                            ),
                        ),
                        ("details", models.JSONField(blank=True, default=dict)),
                        ("timestamp", models.DateTimeField(auto_now_add=True)),
                        (
                            "actor",
                            models.ForeignKey(
                                blank=True,
                                null=True,
                                on_delete=django.db.models.deletion.SET_NULL,
                                related_name="disciplinary_case_audit_events",
                                to=settings.AUTH_USER_MODEL,
                            ),
                        ),
                        (
                            "case",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="audit_events",
                                to="payroll.disciplinarycase",
                            ),
                        ),
                    ],
                    options={
                        "verbose_name": "Disciplinary Case Audit Event",
                        "verbose_name_plural": "Disciplinary Case Audit Events",
                        "db_table": "accounting_disciplinarycaseaudit",
                        "ordering": ["-timestamp", "-id"],
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
                        (
                            "file",
                            models.FileField(
                                blank=True, null=True, upload_to="disciplinary/evidence/"
                            ),
                        ),
                        ("is_confidential", models.BooleanField(default=False)),
                        ("chain_of_custody_notes", models.TextField(blank=True)),
                        (
                            "reliability_score",
                            models.PositiveSmallIntegerField(blank=True, null=True),
                        ),
                        (
                            "case",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="evidence_items",
                                to="payroll.disciplinarycase",
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
                        "db_table": "accounting_disciplinaryevidence",
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
                            "employment_effect_snapshot",
                            models.JSONField(blank=True, default=dict),
                        ),
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
                                    ("PENDING", "Pending approval"),
                                    ("ACTIVE", "Active"),
                                    ("COMPLETED", "Completed"),
                                    ("REVOKED", "Revoked"),
                                ],
                                default="PENDING",
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
                                to="payroll.disciplinarycase",
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
                        "db_table": "accounting_disciplinarysanction",
                        "ordering": ["-created_at"],
                        "base_manager_name": "objects",
                    },
                ),
                migrations.AddIndex(
                    model_name="disciplinarycase",
                    index=models.Index(
                        fields=["case_number"], name="accounting__case_nu_56f812_idx"
                    ),
                ),
                migrations.AddIndex(
                    model_name="disciplinarycase",
                    index=models.Index(fields=["status"], name="accounting__status_8e20af_idx"),
                ),
                migrations.AddIndex(
                    model_name="disciplinarycase",
                    index=models.Index(
                        fields=["violation_level"], name="accounting__violati_445bdd_idx"
                    ),
                ),
                migrations.AddIndex(
                    model_name="disciplinarycase",
                    index=models.Index(
                        fields=["required_review_level"], name="accounting__require_49ca31_idx"
                    ),
                ),
                migrations.AddConstraint(
                    model_name="disciplinarycase",
                    constraint=models.UniqueConstraint(
                        fields=("company", "case_number"), name="uniq_case_company_case_number"
                    ),
                ),
                migrations.AddIndex(
                    model_name="disciplinarycaseaudit",
                    index=models.Index(
                        fields=["case", "timestamp"], name="accounting__case_id_8f8763_idx"
                    ),
                ),
                migrations.AddIndex(
                    model_name="disciplinarycaseaudit",
                    index=models.Index(
                        fields=["actor", "timestamp"], name="accounting__actor_i_57f537_idx"
                    ),
                ),
                migrations.AddIndex(
                    model_name="disciplinarycaseaudit",
                    index=models.Index(
                        fields=["action", "timestamp"], name="accounting__action_6464b1_idx"
                    ),
                ),
            ],
            database_operations=[],
        ),
        migrations.RunPython(forwards, backwards),
    ]
