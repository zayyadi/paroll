from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission  # Added Permission
from django.contrib.contenttypes.models import ContentType  # Added ContentType
from payroll.models import EmployeeProfile, PerformanceReview
from payroll.permissions import (
    setup_groups_and_permissions,
)  # Import the setup function

User = get_user_model()


class EmployeeViewSecurityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Run the permission setup script
        # Note: This will try to create groups. If tests run multiple times without db flush,
        # get_or_create in permissions.py handles it.
        # If permissions.py is run by a post_migrate signal, this might be redundant
        # but ensures permissions are set for the test environment if tests are run isolated.
        setup_groups_and_permissions()

        cls.user = User.objects.create_user(
            email="testuser@example.com",
            password="password123",
            first_name="Test",
            last_name="User",
        )
        cls.admin_user = User.objects.create_superuser(
            email="admin@example.com", password="password123"
        )

        cls.hr_group = Group.objects.get(name="HR")  # Get group created by setup
        cls.hr_user = User.objects.create_user(
            email="hruser@example.com",
            password="password123",
            first_name="HR",
            last_name="Person",
        )
        cls.hr_user.groups.add(cls.hr_group)

        # A user explicitly without any special group or permissions beyond default 'Employee' group if assigned by setup_groups_and_permissions
        cls.no_perm_user = User.objects.create_user(
            email="noperm@example.com",
            password="password123",
            first_name="No",
            last_name="Permission",
        )

        # Assign users to the 'Employee' group if your setup_groups_and_permissions expects it for base perms
        employee_group, _ = Group.objects.get_or_create(name="Employee")
        cls.user.groups.add(employee_group)
        cls.no_perm_user.groups.add(
            employee_group
        )  # Ensure they get whatever 'Employee' group gets

        # Create employee profiles for these users
        cls.employee_profile_user = EmployeeProfile.objects.create(
            user=cls.user,
            email=cls.user.email,
            first_name=cls.user.first_name,
            last_name=cls.user.last_name,
        )
        cls.employee_profile_hr = EmployeeProfile.objects.create(
            user=cls.hr_user,
            email=cls.hr_user.email,
            first_name=cls.hr_user.first_name,
            last_name=cls.hr_user.last_name,
        )
        cls.employee_profile_noperm = EmployeeProfile.objects.create(
            user=cls.no_perm_user,
            email=cls.no_perm_user.email,
            first_name=cls.no_perm_user.first_name,
            last_name=cls.no_perm_user.last_name,
        )
        # Admin user typically does not need an EmployeeProfile unless specific views require it.

    def setUp(self):
        self.client = Client()

    def test_employee_list_requires_login_and_permission(self):
        # Test anonymous access
        response = self.client.get(reverse("payroll:employee_list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("users:login"), response.url)

        # Test with a logged-in user who lacks specific permission (assuming 'Employee' group doesn't have 'view_employeeprofile')
        self.client.login(email="noperm@example.com", password="password123")
        response = self.client.get(reverse("payroll:employee_list"))
        self.assertEqual(
            response.status_code, 403
        )  # Expect Forbidden due to @permission_required

    def test_employee_list_hr_access(self):
        # HR user should have 'payroll.view_employeeprofile' via HR group from setup_groups_and_permissions
        self.client.login(email="hruser@example.com", password="password123")
        response = self.client.get(reverse("payroll:employee_list"))
        self.assertEqual(response.status_code, 200)

    def test_hr_dashboard_restricted_to_hr(self):
        # Test with non-HR user (noperm_user)
        self.client.login(email="noperm@example.com", password="password123")
        response = self.client.get(reverse("payroll:hr_dashboard"))
        # hr_dashboard requires 'payroll.view_employeeprofile'
        self.assertEqual(response.status_code, 403)

        # Test with HR user
        self.client.login(email="hruser@example.com", password="password123")
        response = self.client.get(reverse("payroll:hr_dashboard"))
        self.assertEqual(response.status_code, 200)

    def test_performance_reviews_list_restricted_to_hr(self):
        # Test with non-HR user
        self.client.login(email="noperm@example.com", password="password123")
        response = self.client.get(reverse("payroll:performance_reviews"))
        # performance_reviews requires 'payroll.view_performancereview'
        self.assertEqual(response.status_code, 403)

        # Test with HR user
        self.client.login(email="hruser@example.com", password="password123")
        response = self.client.get(reverse("payroll:performance_reviews"))
        self.assertEqual(response.status_code, 200)

    def test_add_employee_fbv_permission_denial_for_hr(self):
        # HR user has 'payroll.add_employeeprofile' but might lack 'users.add_customuser' based on permissions.py
        # The add_employee FBV requires both.
        # Let's check if HR group has 'users.add_customuser'. If not, this test is valid.
        # From previous setup, HR has: view_customuser, change_customuser. Not add_customuser.
        self.client.login(email="hruser@example.com", password="password123")
        response = self.client.get(
            reverse("payroll:add_employee")
        )  # Assuming this is the FBV
        self.assertEqual(
            response.status_code, 403
        )  # Because it needs users.add_customuser too

    def test_add_employee_fbv_admin_access(self):
        # Superuser has all permissions by default
        self.client.login(email="admin@example.com", password="password123")
        response = self.client.get(
            reverse("payroll:add_employee")
        )  # Assuming this is the FBV
        self.assertEqual(response.status_code, 200)  # FBV renders a form on GET

    # test_employee_list_accessible_to_loggedin_user from original is now covered by more specific permission tests
    # Original test_employee_list_requires_login is covered by test_employee_list_requires_login_and_permission

    # Placeholder for commented out performance_review_detail_access test, can be fleshed out later
    # def test_performance_review_detail_access(self):
    #     pass

    # TODO: Add tests for EmployeeCreateView (CBV) if it has a distinct URL and is used.
    # TODO: Add tests for other views like update_employee, delete_employee (FBV & CBV),
    #       performance_review_detail, add_performance_review, etc., checking both
    #       users with and without specific permissions.
    # TODO: For object-level permission views like `employee` (profile detail), need to test:
    #       1. User accessing their own profile (should be 200).
    #       2. User trying to access another non-HR/admin user's profile (should be 403).
    #       3. HR/Admin user accessing any profile (should be 200).
    #       This requires creating specific instances and testing against them.

    # Example for testing employee profile view (object-level)
    def test_employee_profile_view_own_profile(self):
        self.client.login(email="testuser@example.com", password="password123")
        # Assuming URL for employee profile uses user.id (CustomUser ID)
        response = self.client.get(
            reverse("payroll:employee_profile", args=[self.user.id])
        )
        self.assertEqual(response.status_code, 200)

    def test_employee_profile_view_other_profile_denied(self):
        # noperm_user trying to access testuser's profile
        self.client.login(email="noperm@example.com", password="password123")
        response = self.client.get(
            reverse("payroll:employee_profile", args=[self.user.id])
        )
        self.assertEqual(
            response.status_code, 403
        )  # Denied because no specific view_employeeprofile perm

    def test_employee_profile_view_hr_can_view_other(self):
        self.client.login(email="hruser@example.com", password="password123")
        # HR user trying to access testuser's profile
        # This relies on 'payroll.view_employeeprofile' being assigned to HR group
        response = self.client.get(
            reverse("payroll:employee_profile", args=[self.user.id])
        )
        self.assertEqual(response.status_code, 200)

    def test_employee_profile_view_admin_can_view_other(self):
        self.client.login(email="admin@example.com", password="password123")
        # Admin user trying to access testuser's profile (superuser has all perms)
        response = self.client.get(
            reverse("payroll:employee_profile", args=[self.user.id])
        )
        self.assertEqual(response.status_code, 200)

    # Note: The URL name 'payroll:employee_profile' is an assumption for the employee detail view.
    # It needs to match the actual URL pattern for `payroll.views.employee_view.employee`.
    # If it's different, these tests will fail on URL reversing.

    # Similarly, for performance_review_detail:
    # def test_performance_review_detail_own_review(self):
    #     review = PerformanceReview.objects.create(employee=self.employee_profile_user, review_date='2024-01-01', rating=5)
    #     self.client.login(email='testuser@example.com', password='password123')
    #     response = self.client.get(reverse('payroll:performance_review_detail', args=[review.pk]))
    #     self.assertEqual(response.status_code, 200)

    # def test_performance_review_detail_other_denied(self):
    #     review = PerformanceReview.objects.create(employee=self.employee_profile_user, review_date='2024-01-01', rating=5)
    #     self.client.login(email='noperm@example.com', password='password123')
    #     response = self.client.get(reverse('payroll:performance_review_detail', args=[review.pk]))
    #     self.assertEqual(response.status_code, 403)

    # def test_performance_review_detail_hr_access(self):
    #     review = PerformanceReview.objects.create(employee=self.employee_profile_user, review_date='2024-01-01', rating=5)
    #     self.client.login(email='hruser@example.com', password='password123')
    #     response = self.client.get(reverse('payroll:performance_review_detail', args=[review.pk]))
    #     self.assertEqual(response.status_code, 200)

    # Ensure the URL name 'payroll:performance_review_detail' is correct.
    # And that PerformanceReview model is imported.
    # And that HR group has 'payroll.view_performancereview' permission.
