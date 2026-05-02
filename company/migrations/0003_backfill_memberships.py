from django.db import migrations


def backfill_memberships(apps, schema_editor):
    CustomUser = apps.get_model('users', 'CustomUser')
    CompanyMembership = apps.get_model('company', 'CompanyMembership')

    for user in CustomUser.objects.all().iterator():
        default_company_id = user.active_company_id or user.company_id
        if not default_company_id:
            continue

        CompanyMembership.objects.get_or_create(
            user_id=user.id,
            company_id=default_company_id,
            defaults={'is_default': True, 'role': 'member'},
        )

        CompanyMembership.objects.filter(
            user_id=user.id,
            company_id=user.company_id,
        ).update(is_default=(user.company_id == default_company_id))


class Migration(migrations.Migration):

    dependencies = [
        ('company', '0002_companymembership'),
        ('users', '0004_customuser_active_company'),
    ]

    operations = [
        migrations.RunPython(backfill_memberships, migrations.RunPython.noop),
    ]
