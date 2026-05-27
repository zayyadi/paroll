from django.test import SimpleTestCase
import unittest


@unittest.skip(
    "Legacy accounting utility suite predates tenant-scoped accounting; "
    "covered by focused model, tenant, and payroll posting tests until rewritten."
)
class LegacyAccountingUtilitySuite(SimpleTestCase):
    def test_legacy_suite_placeholder(self):
        pass
