import django.db.models.deletion
from django.db import migrations, models


def set_default_company_for_users(apps, schema_editor):
    Company = apps.get_model('company', 'Company')
    CustomUser = apps.get_model('users', 'CustomUser')

    default_company, _ = Company.objects.get_or_create(
        name='Default Company', defaults={'slug': 'default-company'}
    )
    CustomUser.objects.filter(company__isnull=True).update(company=default_company)


class Migration(migrations.Migration):

    dependencies = [
        ('company', '0001_initial'),
        ('users', '0002_customuser_is_manager'),
    ]

    operations = [
        migrations.AddField(
            model_name='customuser',
            name='company',
            field=models.ForeignKey(
                blank=True,
                db_index=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='users',
                to='company.company',
            ),
        ),
        migrations.RunPython(set_default_company_for_users, migrations.RunPython.noop),
    ]
