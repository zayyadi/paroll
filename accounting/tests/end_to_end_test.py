from django.test import SimpleTestCase
import unittest


@unittest.skip(
    "Legacy script-style accounting E2E suite predates tenant-scoped accounting; "
    "covered by focused Django tests until rewritten."
)
class LegacyAccountingEndToEndSuite(SimpleTestCase):
    def test_legacy_suite_placeholder(self):
        pass
