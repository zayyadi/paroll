"""The disciplinary models moved to payroll (payroll 0095); tables are kept."""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("accounting", "0021_workflow_base_managers"),
        ("payroll", "0095_move_discipline_models"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveField(
                    model_name="disciplinarycase",
                    name="company",
                ),
                migrations.RemoveField(
                    model_name="disciplinarycase",
                    name="decided_by",
                ),
                migrations.RemoveField(
                    model_name="disciplinarycase",
                    name="investigator",
                ),
                migrations.RemoveField(
                    model_name="disciplinarycase",
                    name="reporter",
                ),
                migrations.RemoveField(
                    model_name="disciplinarycase",
                    name="respondent",
                ),
                migrations.RemoveField(
                    model_name="disciplinarysanction",
                    name="case",
                ),
                migrations.RemoveField(
                    model_name="disciplinarycaseaudit",
                    name="case",
                ),
                migrations.RemoveField(
                    model_name="disciplinaryevidence",
                    name="case",
                ),
                migrations.RemoveField(
                    model_name="disciplinarycaseaudit",
                    name="actor",
                ),
                migrations.RemoveField(
                    model_name="disciplinaryevidence",
                    name="submitted_by",
                ),
                migrations.RemoveField(
                    model_name="disciplinarysanction",
                    name="created_by",
                ),
                migrations.DeleteModel(
                    name="DisciplinaryAppeal",
                ),
                migrations.DeleteModel(
                    name="DisciplinaryCase",
                ),
                migrations.DeleteModel(
                    name="DisciplinaryCaseAudit",
                ),
                migrations.DeleteModel(
                    name="DisciplinaryEvidence",
                ),
                migrations.DeleteModel(
                    name="DisciplinarySanction",
                ),
            ],
            database_operations=[],
        ),
    ]
