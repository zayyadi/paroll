from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [("payroll", "0074_review_publication_state")]
    operations = [migrations.AlterField(model_name="joboffer", name="status",
        field=models.CharField(max_length=20, default="draft", choices=[("draft", "Draft"), ("sent", "Sent"), ("accepted", "Accepted"), ("declined", "Declined"), ("withdrawn", "Withdrawn")]))]
