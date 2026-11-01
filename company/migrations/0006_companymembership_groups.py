from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("company", "0005_workflow_base_managers"),
    ]

    operations = [
        migrations.AddField(
            model_name="companymembership",
            name="groups",
            field=models.ManyToManyField(
                blank=True,
                help_text=(
                    "Permission groups the user holds in this company. When empty, the "
                    "user's own groups apply in their primary company, and owners and "
                    "admins get the Admin group elsewhere."
                ),
                related_name="company_memberships",
                to="auth.group",
            ),
        ),
    ]
