from django.db import migrations, models
import django.db.models.deletion


def backfill_disciplinary_case_company(apps, schema_editor):
    DisciplinaryCase = apps.get_model("accounting", "DisciplinaryCase")

    for case in DisciplinaryCase.objects.select_related("respondent", "reporter"):
        company_id = None
        if case.respondent_id:
            company_id = case.respondent.active_company_id or case.respondent.company_id
        if company_id is None and case.reporter_id:
            company_id = case.reporter.active_company_id or case.reporter.company_id
        if company_id is not None:
            case.company_id = company_id
            case.save(update_fields=["company"])


class Migration(migrations.Migration):

    dependencies = [
        ("accounting", "0006_financialreportline_formula_and_more"),
        ("company", "0003_backfill_memberships"),
    ]

    operations = [
        migrations.AddField(
            model_name="disciplinarycase",
            name="company",
            field=models.ForeignKey(
                blank=True,
                db_index=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="disciplinary_cases",
                to="company.company",
            ),
        ),
        migrations.RunPython(
            backfill_disciplinary_case_company, migrations.RunPython.noop
        ),
    ]
