"""Inventory is hidden unless INVENTORY_ENABLED is on."""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from company.models import Company


class InventoryFeatureFlagTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Flag Co")
        self.user = get_user_model().objects.create_superuser(
            email="flag-admin@example.com",
            password="x",
            company=self.company,
            active_company=self.company,
        )
        self.client.force_login(self.user)

    @override_settings(INVENTORY_ENABLED=False)
    def test_pages_and_api_return_404_when_disabled(self):
        self.assertEqual(self.client.get(reverse("inventory:dashboard")).status_code, 404)
        self.assertEqual(self.client.get("/api/v1/inventory/items/").status_code, 404)
        self.assertEqual(self.client.get("/api/inventory/items/").status_code, 404)

    @override_settings(INVENTORY_ENABLED=False)
    def test_sidebar_omits_inventory_when_disabled(self):
        response = self.client.get(reverse("payroll:index"), follow=True)
        self.assertNotContains(response, reverse("inventory:dashboard"))

    @override_settings(INVENTORY_ENABLED=False)
    def test_inventory_urls_still_reverse_when_disabled(self):
        # Records elsewhere (e.g. approval requests) may link to inventory.
        self.assertTrue(reverse("inventory:item_list"))

    @override_settings(INVENTORY_ENABLED=True)
    def test_enabled_restores_pages_and_sidebar(self):
        self.assertEqual(self.client.get(reverse("inventory:dashboard")).status_code, 200)
        response = self.client.get(reverse("payroll:index"), follow=True)
        self.assertContains(response, reverse("inventory:dashboard"))
