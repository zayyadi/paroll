"""API token scopes (P1-10).

Gap #10 of docs/world_class_employee_management_research_2026-10-14.md: scope
tokens to resource groups before external integrators are onboarded.

A *scope* is a named grant over a group of resources (``employee:read``,
``payroll:write``, ...). The URL-prefix → scope table in
:data:`RESOURCE_GROUP_SCOPES` maps every registered ``api/v1`` route to the
scope required to reach it, grouped by the resource families the API already
serves (employees, payroll, leave, accounting, inventory, standups).

``TokenScopePermission`` is a DRF permission that, when the request carries an
API token (``request.auth.scope`` is a set of scope strings), enforces that
the token holds the scope for the route. Session/JWT users (humans in the
browser/app) are unaffected — they are governed by the existing role
permissions, so this is purely additive and cannot regress logged-in flows.
"""
from __future__ import annotations

from rest_framework.permissions import BasePermission

# Every scope this deployment understands. ``*`` is the wildcard granting all.
ALL_SCOPES = (
    "employee:read",
    "employee:write",
    "payroll:read",
    "payroll:write",
    "leave:read",
    "leave:write",
    "accounting:read",
    "accounting:write",
    "inventory:read",
    "inventory:write",
    "standup:read",
    "standup:write",
    "*",
)

# URL-prefix → required scope. Longest prefix wins, so "inventory/" entries
# are checked before any broader fallback. Read-only verbs (GET/HEAD/OPTIONS)
# accept the matching ``:read`` scope; writes need ``:write``.
RESOURCE_GROUP_SCOPES: dict = {
    "employees": {"read": "employee:read", "write": "employee:write"},
    "departments": {"read": "employee:read", "write": "employee:write"},
    "payrolls": {"read": "payroll:read", "write": "payroll:write"},
    "payroll-entries": {"read": "payroll:read", "write": "payroll:write"},
    "payroll-runs": {"read": "payroll:read", "write": "payroll:write"},
    "leave-policies": {"read": "leave:read", "write": "leave:write"},
    "leave-requests": {"read": "leave:read", "write": "leave:write"},
    "ious": {"read": "payroll:read", "write": "payroll:write"},
    "accounts": {"read": "accounting:read", "write": "accounting:write"},
    "fiscal-years": {"read": "accounting:read", "write": "accounting:write"},
    "accounting-periods": {
        "read": "accounting:read",
        "write": "accounting:write",
    },
    "journals": {"read": "accounting:read", "write": "accounting:write"},
    "journal-entries": {
        "read": "accounting:read",
        "write": "accounting:write",
    },
    "inventory/": {"read": "inventory:read", "write": "inventory:write"},
    "standup-": {"read": "standup:read", "write": "standup:write"},
    "auth/": {"read": None, "write": None},  # never scope-gated
    "mobile/": {"read": None, "write": None},
    "schema": {"read": None, "write": None},
    "docs/": {"read": None, "write": None},
}

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def required_scope(path: str, method: str) -> str | None:
    """Return the scope a request to ``path`` with ``method`` needs, or None.

    Longest-prefix match over :data:`RESOURCE_GROUP_SCOPES`. ``None`` means the
    route is not scope-gated (auth/schema/docs/mobile).
    """
    # Strip the version prefix and leading slash: /api/v1/employees/ -> employees/
    parts = path.strip("/").split("/")
    if parts and parts[0] == "api":
        parts = parts[1:]
    if parts and parts[0].startswith("v") and parts[0][1:].isdigit():
        parts = parts[1:]
    remainder = "/".join(parts)

    best_prefix = ""
    best_group = None
    for prefix, group in RESOURCE_GROUP_SCOPES.items():
        if remainder.startswith(prefix) and len(prefix) > len(best_prefix):
            best_prefix = prefix
            best_group = group
    if best_group is None:
        return None
    verb = "read" if method.upper() in SAFE_METHODS else "write"
    return best_group.get(verb)


def _scope_satisfied(needed: str, granted: set) -> bool:
    """True when ``granted`` covers ``needed``.

    A write scope implies its read counterpart: holding ``employee:write``
    also permits ``employee:read``. ``*`` covers everything (checked by the
    caller before this helper is reached, but kept here for safety).
    """
    if needed in granted or "*" in granted:
        return True
    group, verb = needed.rsplit(":", 1)
    if verb == "read" and f"{group}:write" in granted:
        return True
    return False


def token_scopes(request) -> set | None:
    """The set of scopes on the request's token, or None for non-token auth.

    Token authenticators are expected to stash the granted scopes on
    ``request.auth.scopes``. Session/JWT users have no ``scopes`` attribute,
    so this returns None and the permission defers to role checks.
    """
    auth = getattr(request, "auth", None)
    if auth is None:
        return None
    scopes = getattr(auth, "scopes", None)
    if scopes is None:
        return None
    return set(scopes)


class TokenScopePermission(BasePermission):
    """Enforce token scopes; no-op for session/JWT (human) requests.

    A request carrying a scoped token must hold the scope mapped to its route
    (or the ``*`` wildcard). Requests with no token scopes (humans) pass
    through so existing role permissions remain the source of truth.
    """

    message = "This API token does not grant the required scope."

    def has_permission(self, request, view):
        scopes = token_scopes(request)
        if scopes is None:
            # Not a scoped token — defer to the other permission classes.
            return True
        if "*" in scopes:
            return True
        needed = required_scope(request.path, request.method)
        if needed is None:
            return True
        return _scope_satisfied(needed, scopes)
