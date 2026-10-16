from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("payroll", "0073_payrollrunentry_unique_payroll_run_entry"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.AddField(model_name="review", name="status", field=models.CharField(choices=[("DRAFT", "Draft"), ("SUBMITTED", "Awaiting publication approval"), ("PUBLISHED", "Published"), ("ARCHIVED", "Archived")], default="DRAFT", max_length=20)),
        migrations.AddField(model_name="review", name="published_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="review", name="published_by", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="published_reviews", to=settings.AUTH_USER_MODEL)),
        migrations.AlterModelOptions(name="review", options={"permissions": [("publish_review", "Can approve publication of employee reviews")]}),
    ]
