from django.test import SimpleTestCase
import unittest


@unittest.skip(
    "Legacy accounting integration suite predates tenant-scoped accounting; "
    "covered by test_tenant_scoping and test_payroll_postings until rewritten."
)
class LegacyAccountingIntegrationSuite(SimpleTestCase):
    def test_legacy_suite_placeholder(self):
        pass
