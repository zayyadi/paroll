"""Permissions apply only in the user's active company (CompanyScopedModelBackend)."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase, override_settings

from company.models import Company, CompanyMembership

VIEW_PAYROLL = "payroll.view_payroll"


def _perm(codename):
    return Permission.objects.get(content_type__app_label="payroll", codename=codename)


@override_settings(MULTI_COMPANY_MEMBERSHIP_ENABLED=True)
class CompanyScopedPermissionTests(TestCase):
    def setUp(self):
        self.company_a = Company.objects.create(name="Company A")
        self.company_b = Company.objects.create(name="Company B")
        self.hr_group = Group.objects.create(name="HR test")
        self.hr_group.permissions.add(_perm("view_payroll"))
        self.admin_group, _ = Group.objects.get_or_create(name="Admin")
        self.admin_group.permissions.add(_perm("change_payroll"))

        self.user = get_user_model().objects.create_user(
            email="multi@example.com",
            password="pw",
            company=self.company_a,
            active_company=self.company_a,
        )
        self.user.groups.add(self.hr_group)
        CompanyMembership.objects.get_or_create(user=self.user, company=self.company_a)

    def _switch_to(self, company):
        self.user.active_company = company
        self.user.save(update_fields=["active_company"])
        return get_user_model().objects.get(pk=self.user.pk)  # fresh permission cache

    def test_own_groups_apply_in_primary_company(self):
        self.assertTrue(self.user.has_perm(VIEW_PAYROLL))

    def test_own_groups_do_not_follow_into_another_company(self):
        CompanyMembership.objects.create(user=self.user, company=self.company_b)

        user = self._switch_to(self.company_b)

        self.assertFalse(user.has_perm(VIEW_PAYROLL))

    def test_membership_groups_grant_permissions_in_that_company_only(self):
        membership = CompanyMembership.objects.create(user=self.user, company=self.company_b)
        payroll_viewers = Group.objects.create(name="Company B payroll")
        payroll_viewers.permissions.add(_perm("view_payrollrun"))
        membership.groups.add(payroll_viewers)

        user = self._switch_to(self.company_b)

        self.assertTrue(user.has_perm("payroll.view_payrollrun"))
        self.assertFalse(user.has_perm(VIEW_PAYROLL))

    def test_owner_without_groups_gets_admin_group_in_secondary_company(self):
        CompanyMembership.objects.create(
            user=self.user, company=self.company_b, role=CompanyMembership.ROLE_OWNER
        )

        user = self._switch_to(self.company_b)

        self.assertTrue(user.has_perm("payroll.change_payroll"))
        self.assertFalse(user.has_perm(VIEW_PAYROLL))

    def test_company_without_membership_falls_back_to_primary(self):
        # Saving active_company creates a membership, so set it directly to
        # simulate a stale pointer at a company the user does not belong to.
        get_user_model().objects.filter(pk=self.user.pk).update(active_company=self.company_b)
        user = get_user_model().objects.get(pk=self.user.pk)

        self.assertTrue(user.has_perm(VIEW_PAYROLL))  # acts in primary company A

    def test_no_company_grants_nothing(self):
        CompanyMembership.objects.filter(user=self.user).delete()
        get_user_model().objects.filter(pk=self.user.pk).update(company=None, active_company=None)
        user = get_user_model().objects.get(pk=self.user.pk)

        self.assertFalse(user.has_perm(VIEW_PAYROLL))

    def test_superuser_keeps_every_permission(self):
        admin = get_user_model().objects.create_superuser(email="root@example.com", password="pw")

        self.assertTrue(admin.has_perm(VIEW_PAYROLL))


class SingleCompanyModeTests(TestCase):
    """With multi-company membership off, behaviour matches ModelBackend."""

    def test_user_groups_apply_in_their_company(self):
        company = Company.objects.create(name="Solo Co")
        group = Group.objects.create(name="Solo HR")
        group.permissions.add(_perm("view_payroll"))
        user = get_user_model().objects.create_user(
            email="solo@example.com", password="pw", company=company, active_company=company
        )
        user.groups.add(group)

        self.assertTrue(get_user_model().objects.get(pk=user.pk).has_perm(VIEW_PAYROLL))
