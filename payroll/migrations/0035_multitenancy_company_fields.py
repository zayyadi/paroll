import django.db.models.deletion
from django.db import migrations, models


def backfill_company_on_payroll_models(apps, schema_editor):
    Company = apps.get_model('company', 'Company')
    Department = apps.get_model('payroll', 'Department')
    EmployeeProfile = apps.get_model('payroll', 'EmployeeProfile')
    Payroll = apps.get_model('payroll', 'Payroll')
    PayrollEntry = apps.get_model('payroll', 'PayrollEntry')
    PayrollRun = apps.get_model('payroll', 'PayrollRun')

    default_company, _ = Company.objects.get_or_create(
        name='Default Company', defaults={'slug': 'default-company'}
    )

    for employee in EmployeeProfile.objects.select_related('user').all().iterator():
        company_id = default_company.id
        if employee.user_id and getattr(employee.user, 'company_id', None):
            company_id = employee.user.company_id
        if employee.company_id != company_id:
            employee.company_id = company_id
            employee.save(update_fields=['company'])

    for department in Department.objects.filter(company__isnull=True).iterator():
        employee = (
            EmployeeProfile.objects.filter(department_id=department.id)
            .exclude(company__isnull=True)
            .first()
        )
        department.company_id = employee.company_id if employee else default_company.id
        department.save(update_fields=['company'])

    for payroll in Payroll.objects.filter(company__isnull=True).iterator():
        employee = (
            EmployeeProfile.objects.filter(employee_pay_id=payroll.id)
            .exclude(company__isnull=True)
            .first()
        )
        payroll.company_id = employee.company_id if employee else default_company.id
        payroll.save(update_fields=['company'])

    for entry in PayrollEntry.objects.filter(company__isnull=True).iterator():
        entry.company_id = entry.pays.company_id if entry.pays_id else default_company.id
        entry.save(update_fields=['company'])

    for payroll_run in PayrollRun.objects.filter(company__isnull=True).iterator():
        first_entry = payroll_run.payroll_payday.exclude(company__isnull=True).first()
        payroll_run.company_id = (
            first_entry.company_id if first_entry else default_company.id
        )
        payroll_run.save(update_fields=['company'])


class Migration(migrations.Migration):

    dependencies = [
        ('company', '0001_initial'),
        ('users', '0003_customuser_company'),
        ('payroll', '0034_alter_payrollrun_options_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='department',
            name='company',
            field=models.ForeignKey(
                blank=True,
                db_index=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='departments',
                to='company.company',
            ),
        ),
        migrations.AlterUniqueTogether(
            name='department',
            unique_together={('company', 'name')},
        ),
        migrations.AddField(
            model_name='employeeprofile',
            name='company',
            field=models.ForeignKey(
                blank=True,
                db_index=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='employees',
                to='company.company',
            ),
        ),
        migrations.AddField(
            model_name='payroll',
            name='company',
            field=models.ForeignKey(
                blank=True,
                db_index=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='payroll_configs',
                to='company.company',
            ),
        ),
        migrations.AddField(
            model_name='payrollentry',
            name='company',
            field=models.ForeignKey(
                blank=True,
                db_index=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='payroll_entries',
                to='company.company',
            ),
        ),
        migrations.AddField(
            model_name='payrollrun',
            name='company',
            field=models.ForeignKey(
                blank=True,
                db_index=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='payroll_runs',
                to='company.company',
            ),
        ),
        migrations.AlterField(
            model_name='payrollrun',
            name='name',
            field=models.CharField(default='test', max_length=50),
        ),
        migrations.AlterField(
            model_name='payrollrun',
            name='slug',
            field=models.SlugField(db_index=True, editable=False, max_length=255),
        ),
        migrations.AlterUniqueTogether(
            name='payrollrun',
            unique_together={('company', 'name'), ('company', 'slug')},
        ),
        migrations.RunPython(backfill_company_on_payroll_models, migrations.RunPython.noop),
    ]
