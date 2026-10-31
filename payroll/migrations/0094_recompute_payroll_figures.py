"""Recompute stored payroll figures after the statutory changes.

NHIA and NSITF were stored monthly while every other statutory figure was
annual; pension was charged on full gross; net pay ignored pension and the
part of gross outside basic/housing/transport. ``Payroll.save`` now derives
consistent annual figures, so re-save every config and refresh net pay.

Runs after the NHF consent and rent declaration migrations so the recomputed
PAYE reflects consent and approved rent. This deliberately calls the live
service (not historical models): the derivation is application logic, so it
must stay the last payroll migration until its rows are recomputed. On a
fresh database there are no rows and nothing runs.
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
        ("payroll", "0093_exit_settlement_tax"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
