"""Recompute stored payroll figures under the annual-units convention.

NHIA and NSITF were stored monthly while every other statutory figure was
annual; pension was charged on full gross; net pay ignored pension and the
part of gross outside basic/housing/transport. ``Payroll.save`` now derives
consistent annual figures, so re-save every config and refresh net pay.

This deliberately calls the live service (not historical models): the
derivation is application logic. On a fresh database there are no rows and
nothing runs.
"""

from django.db import migrations


def forwards(apps, schema_editor):
    Payroll = apps.get_model("payroll", "Payroll")
    if not Payroll.objects.exists():
        return
    from payroll.services.payroll_recompute import recompute_payroll_figures

    recompute_payroll_figures(apply=True)


class Migration(migrations.Migration):
    dependencies = [
        ("payroll", "0088_productise_leave_catalogue"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
