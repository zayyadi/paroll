import django.db.models.deletion
from django.db import migrations, models


def backfill_accounting_companies(apps, schema_editor):
    Company = apps.get_model("company", "Company")
    Account = apps.get_model("accounting", "Account")
    FiscalYear = apps.get_model("accounting", "FiscalYear")
    AccountingPeriod = apps.get_model("accounting", "AccountingPeriod")
    Journal = apps.get_model("accounting", "Journal")
    AccountingAuditTrail = apps.get_model("accounting", "AccountingAuditTrail")

    company, _ = Company.objects.get_or_create(name="Default Company")

    Account.objects.filter(company__isnull=True).update(company=company)
    FiscalYear.objects.filter(company__isnull=True).update(company=company)

    for period in AccountingPeriod.objects.filter(company__isnull=True).select_related(
        "fiscal_year"
    ):
        period.company_id = period.fiscal_year.company_id or company.id
        period.save(update_fields=["company"])

    for journal in Journal.objects.filter(company__isnull=True).select_related("period"):
        journal.company_id = journal.period.company_id or company.id
        journal.save(update_fields=["company"])

    AccountingAuditTrail.objects.filter(company__isnull=True).update(company=company)


class Migration(migrations.Migration):

    dependencies = [
        ("company", "0003_backfill_memberships"),
        ("accounting", "0003_rename_acct_disc_case_idx_accounting__case_nu_56f812_idx_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="account",
            name="company",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="accounts",
                to="company.company",
            ),
        ),
        migrations.AddField(
            model_name="fiscalyear",
            name="company",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="fiscal_years",
                to="company.company",
            ),
        ),
        migrations.AddField(
            model_name="accountingperiod",
            name="company",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="accounting_periods",
                to="company.company",
            ),
        ),
        migrations.AddField(
            model_name="accountingaudittrail",
            name="company",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="accounting_audit_trails",
                to="company.company",
            ),
        ),
        migrations.AddField(
            model_name="journal",
            name="company",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="journals",
                to="company.company",
            ),
        ),
        migrations.RunPython(backfill_accounting_companies, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="account",
            name="company",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="accounts",
                to="company.company",
            ),
        ),
        migrations.AlterField(
            model_name="account",
            name="name",
            field=models.CharField(max_length=255),
        ),
        migrations.AlterField(
            model_name="account",
            name="account_number",
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
        migrations.AlterField(
            model_name="fiscalyear",
            name="company",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="fiscal_years",
                to="company.company",
            ),
        ),
        migrations.AlterField(
            model_name="fiscalyear",
            name="year",
            field=models.PositiveIntegerField(),
        ),
        migrations.AlterField(
            model_name="accountingperiod",
            name="company",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="accounting_periods",
                to="company.company",
            ),
        ),
        migrations.AlterField(
            model_name="journal",
            name="company",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="journals",
                to="company.company",
            ),
        ),
        migrations.AlterUniqueTogether(
            name="accountingperiod",
            unique_together=set(),
        ),
        migrations.AddConstraint(
            model_name="account",
            constraint=models.UniqueConstraint(
                fields=("company", "name"), name="uniq_account_company_name"
            ),
        ),
        migrations.AddConstraint(
            model_name="account",
            constraint=models.UniqueConstraint(
                fields=("company", "account_number"),
                name="uniq_account_company_account_number",
            ),
        ),
        migrations.AddConstraint(
            model_name="fiscalyear",
            constraint=models.UniqueConstraint(
                fields=("company", "year"), name="uniq_fiscal_year_company_year"
            ),
        ),
        migrations.AddConstraint(
            model_name="accountingperiod",
            constraint=models.UniqueConstraint(
                fields=("company", "fiscal_year", "period_number"),
                name="uniq_period_company_fiscal_year_number",
            ),
        ),
    ]
