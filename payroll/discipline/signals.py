"""Wire HR employment effects to ledger-stored sanctions.

The tables still live in ``accounting`` until the data migration lands;
this signal is the only allowed accounting → HR edge, inverted so the
ledger never imports payroll.
"""

from __future__ import annotations

from django.db.models.signals import post_save
from django.dispatch import receiver

from accounting.models import DisciplinarySanction

from .services import apply_termination_effects


@receiver(post_save, sender=DisciplinarySanction)
def apply_employment_effects_on_sanction_save(sender, instance, **kwargs):
    apply_termination_effects(instance)
