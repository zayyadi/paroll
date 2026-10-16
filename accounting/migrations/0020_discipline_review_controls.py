from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [("accounting", "0019_journal_approval_request_and_more")]
    operations = [
        migrations.AlterModelOptions(name="disciplinarycase", options={"ordering":["-created_at"], "verbose_name":"Disciplinary Case", "verbose_name_plural":"Disciplinary Cases",
            "permissions":[("review_hr_disciplinarycase","Can approve HR lead disciplinary decisions"),
                ("review_panel_disciplinarycase","Can approve panel disciplinary decisions"),
                ("review_executive_disciplinarycase","Can approve executive disciplinary decisions")]}),
        migrations.AddField(model_name="disciplinarysanction", name="employment_effect_snapshot", field=models.JSONField(default=dict,blank=True)),
    ]
