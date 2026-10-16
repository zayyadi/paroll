"""Tests for API versioning and token scopes (P1-10).

Gap #10 of docs/world_class_employee_management_research_2026-10-14.md:
publish a versioning rule and scope tokens to resource groups.
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase

from api.scopes import required_scope
from api.versioning import (
    CURRENT_VERSION,
    SUPPORTED_VERSIONS,
    is_supported_version,
    parse_version,
)
from company.models import Company


class VersionParsingTests(TestCase):
    def test_parse_version_handles_v1(self):
        self.assertEqual(parse_version("v1"), 1)
        self.assertEqual(parse_version("V2"), 2)

    def test_parse_version_rejects_garbage(self):
        self.assertIsNone(parse_version("banana"))
        self.assertIsNone(parse_version(""))
        self.assertIsNone(parse_version(None))
        self.assertIsNone(parse_version("1"))

    def test_current_version_is_supported(self):
        self.assertIn(CURRENT_VERSION, SUPPORTED_VERSIONS)

    def test_is_supported_version(self):
        self.assertTrue(is_supported_version("v1"))
        self.assertFalse(is_supported_version("v99"))


class VersionMiddlewareTests(TestCase):
    """The /api/<version>/ path is the authoritative version selector."""

    def setUp(self):
        self.company = Company.objects.create(name="Version Co")
        self.user = get_user_model().objects.create_user(
            email="ver@example.com",
            password="password123",
            company=self.company,
            active_company=self.company,
        )
        self.client.force_login(self.user)

    def test_supported_version_stamps_response_header(self):
        response = self.client.get("/api/v1/auth/companies/")
        self.assertIn("X-API-Version", response.headers)
        self.assertEqual(response.headers["X-API-Version"], "v1")

    def test_unsupported_version_rejected_with_400(self):
        response = self.client.get("/api/v99/auth/companies/")
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertIn("v99", body["detail"])
        self.assertEqual(body["current_version"], "v1")
        self.assertIn("v1", body["supported_versions"])

    def test_non_api_paths_pass_through(self):
        response = self.client.get("/webhooks/changed-employees/")
        # Not an API path: middleware leaves it alone (no version header
        # stamped). The view itself may still return its own 400 for a
        # missing 'since' param — that is unrelated to versioning.
        self.assertNotIn("X-API-Version", response.headers)


class ScopeResolutionTests(TestCase):
    def test_read_maps_to_read_scope(self):
        self.assertEqual(
            required_scope("/api/v1/employees/", "GET"), "employee:read"
        )
        self.assertEqual(
            required_scope("/api/v1/journals/", "GET"), "accounting:read"
        )
        self.assertEqual(
            required_scope("/api/v1/inventory/items/", "GET"), "inventory:read"
        )

    def test_write_maps_to_write_scope(self):
        self.assertEqual(
            required_scope("/api/v1/employees/", "POST"), "employee:write"
        )
        self.assertEqual(
            required_scope("/api/v1/payroll-runs/", "DELETE"),
            "payroll:write",
        )
        self.assertEqual(
            required_scope("/api/v1/leave-requests/", "PATCH"), "leave:write"
        )

    def test_longest_prefix_wins_for_inventory(self):
        # inventory/ is a prefix of nothing shorter that would win.
        self.assertEqual(
            required_scope("/api/v1/inventory/movements/", "GET"),
            "inventory:read",
        )

    def test_ungated_routes_return_none(self):
        self.assertIsNone(required_scope("/api/v1/auth/companies/", "GET"))
        self.assertIsNone(required_scope("/api/v1/schema/", "GET"))
        self.assertIsNone(required_scope("/api/v1/docs/swagger/", "GET"))


class TokenScopePermissionTests(TestCase):
    """Scope enforcement is additive: humans pass, scoped tokens are gated."""

    def _request(self, path, method="GET", scopes=None):
        class Req:
            pass

        req = Req()
        req.path = path
        req.method = method
        if scopes is not None:
            auth = type("Auth", (), {})()
            auth.scopes = scopes
            req.auth = auth
        else:
            req.auth = None  # session/JWT user
        return req

    def _perm(self):
        from api.scopes import TokenScopePermission

        return TokenScopePermission()

    def test_session_user_defers_to_role_checks(self):
        req = self._request("/api/v1/employees/", "GET", scopes=None)
        self.assertTrue(self._perm().has_permission(req, None))

    def test_token_with_matching_scope_allowed(self):
        req = self._request(
            "/api/v1/employees/", "GET", scopes={"employee:read"}
        )
        self.assertTrue(self._perm().has_permission(req, None))

    def test_token_with_write_scope_allows_read(self):
        req = self._request(
            "/api/v1/employees/", "GET", scopes={"employee:write"}
        )
        self.assertTrue(self._perm().has_permission(req, None))

    def test_token_missing_scope_denied(self):
        req = self._request(
            "/api/v1/employees/", "POST", scopes={"inventory:read"}
        )
        self.assertFalse(self._perm().has_permission(req, None))

    def test_wildcard_grants_everything(self):
        req = self._request(
            "/api/v1/payroll-runs/", "DELETE", scopes={"*"}
        )
        self.assertTrue(self._perm().has_permission(req, None))

    def test_write_scope_does_not_grant_other_group(self):
        # employee:write should not open the accounting door.
        req = self._request(
            "/api/v1/journals/", "POST", scopes={"employee:write"}
        )
        self.assertFalse(self._perm().has_permission(req, None))
