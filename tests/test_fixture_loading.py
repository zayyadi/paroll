from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from payroll.signals import create_iou_deduction_for_payroll_entry_signal


class FixtureLoadingSignalTests(SimpleTestCase):
    def test_payroll_run_entry_signal_skips_raw_fixture_loads(self):
        with patch("payroll.signals._create_iou_deduction_for_payroll_entry") as service:
            create_iou_deduction_for_payroll_entry_signal(
                sender=None,
                instance=Mock(),
                created=True,
                raw=True,
            )

        service.assert_not_called()
