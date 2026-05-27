from django.test import SimpleTestCase
import unittest


@unittest.skip(
    "Legacy accounting performance suite predates tenant-scoped accounting; "
    "rewrite with company-scoped factories before re-enabling."
)
class LegacyAccountingPerformanceSuite(SimpleTestCase):
    def test_legacy_suite_placeholder(self):
        pass
