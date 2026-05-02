import django.db.models.deletion
from django.db import migrations, models


def backfill_active_company(apps, schema_editor):
    CustomUser = apps.get_model('users', 'CustomUser')
    for user in CustomUser.objects.filter(active_company__isnull=True).iterator():
        if user.company_id:
            user.active_company_id = user.company_id
            user.save(update_fields=['active_company'])


class Migration(migrations.Migration):

    dependencies = [
        ('company', '0001_initial'),
        ('users', '0003_customuser_company'),
    ]

    operations = [
        migrations.AddField(
            model_name='customuser',
            name='active_company',
            field=models.ForeignKey(
                blank=True,
                db_index=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='active_users',
                to='company.company',
            ),
        ),
        migrations.RunPython(backfill_active_company, migrations.RunPython.noop),
    ]
