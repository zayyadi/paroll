"""Company-scoped Django permissions.

``ModelBackend`` grants a user's groups and permissions everywhere. In a
multi-company workspace that would let an HR user in one company act as HR in
every company they can switch to. This backend applies permissions only in the
user's active company:

- Primary company (``user.company``): the user's own groups and permissions,
  unless the membership lists groups, which then replace them.
- Any other company: the groups on that ``CompanyMembership``. Owners and
  admins with no groups listed get the ``Admin`` group's permissions; plain
  members get none.
- No active company, or an active company the user does not belong to: none.

Superusers keep every permission. Authentication itself is unchanged.
"""

from django.conf import settings
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.models import Permission

ADMIN_GROUP_NAME = "Admin"
_CACHE_ATTR = "_company_perm_cache"


def active_company_id(user) -> int | None:
    """The company the user is acting in, without side effects.

    Mirrors ``company.utils.get_user_company`` (which also sets the request's
    company context, so it is not used here).
    """
    from company.models import CompanyMembership

    primary_id = getattr(user, "company_id", None)
    if not getattr(settings, "MULTI_COMPANY_MEMBERSHIP_ENABLED", False):
        return primary_id or getattr(user, "active_company_id", None)
    memberships = CompanyMembership.objects.filter(user=user)
    active_id = getattr(user, "active_company_id", None)
    if active_id and memberships.filter(company_id=active_id).exists():
        return active_id
    if primary_id and memberships.filter(company_id=primary_id).exists():
        return primary_id
    first = memberships.order_by("-is_default", "company__name").values_list("company_id", flat=True).first()
    return first


def _perm_names(queryset) -> set[str]:
    return {
        f"{app_label}.{codename}"
        for app_label, codename in queryset.values_list("content_type__app_label", "codename")
    }


class CompanyScopedModelBackend(ModelBackend):
    def _company_permissions(self, user_obj, company_id) -> set[str]:
        from company.models import CompanyMembership

        membership = (
            CompanyMembership.objects.filter(user=user_obj, company_id=company_id)
            .prefetch_related("groups")
            .first()
        )
        is_primary = company_id == getattr(user_obj, "company_id", None)
        if membership is None and not is_primary:
            return set()

        if membership is not None and membership.groups.exists():
            group_perms = _perm_names(Permission.objects.filter(group__in=membership.groups.all()))
            return group_perms | self.get_user_permissions(user_obj)
        if is_primary:
            return super().get_all_permissions(user_obj)
        if membership.role in (CompanyMembership.ROLE_OWNER, CompanyMembership.ROLE_ADMIN):
            return _perm_names(Permission.objects.filter(group__name=ADMIN_GROUP_NAME))
        return set()

    def get_all_permissions(self, user_obj, obj=None):
        if not user_obj.is_active or user_obj.is_anonymous or obj is not None:
            return set()
        if user_obj.is_superuser:
            return super().get_all_permissions(user_obj, obj)

        company_id = active_company_id(user_obj)
        cached = getattr(user_obj, _CACHE_ATTR, None)
        # Code that grants a permission and then clears Django's standard
        # caches (``_perm_cache`` etc.) must invalidate this one too.
        if cached is not None and cached[0] == company_id and hasattr(user_obj, "_perm_cache"):
            return cached[1]
        for attr in ("_perm_cache", "_user_perm_cache", "_group_perm_cache"):
            user_obj.__dict__.pop(attr, None)
        perms = self._company_permissions(user_obj, company_id) if company_id else set()
        user_obj._perm_cache = perms
        setattr(user_obj, _CACHE_ATTR, (company_id, perms))
        return perms
