from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("payroll", "0071_water_rate_settings"),
    ]

    operations = [
        migrations.DeleteModel(name="CompanyChatReadState"),
        migrations.DeleteModel(name="CompanyChatRoomMember"),
        migrations.DeleteModel(name="CompanyChatMessage"),
        migrations.DeleteModel(name="CompanyChatRoom"),
    ]
