from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [("payroll", "0076_payrollrun_currency_payrollrun_requested_by"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [migrations.AddField(model_name=name, name="requested_by", field=models.ForeignKey(blank=True, null=True,
        on_delete=django.db.models.deletion.PROTECT, related_name="created_"+name+"_requests", to=settings.AUTH_USER_MODEL))
        for name in ("leaverequest", "iou", "overtimeentry")]
