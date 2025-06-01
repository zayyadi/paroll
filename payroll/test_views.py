from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group # Corrected import for Group
from payroll.models import EmployeeProfile, PerformanceReview # Added PerformanceReview

User = get_user_model()

class EmployeeViewSecurityTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(email='testuser@example.com', password='password123', first_name='Test', last_name='User')
        self.admin_user = User.objects.create_superuser(email='admin@example.com', password='password123')

        # Create HR group and assign a user to it
        self.hr_group, _ = Group.objects.get_or_create(name='HR')
        self.hr_user = User.objects.create_user(email='hruser@example.com', password='password123', first_name='HR', last_name='Person')
        self.hr_user.groups.add(self.hr_group)

        # Create employee profiles for these users
        self.employee_profile = EmployeeProfile.objects.create(user=self.user, email=self.user.email, first_name=self.user.first_name, last_name=self.user.last_name)
        # It's good practice to also create a profile for the HR user if views might expect it
        self.hr_employee_profile = EmployeeProfile.objects.create(user=self.hr_user, email=self.hr_user.email, first_name=self.hr_user.first_name, last_name=self.hr_user.last_name)
        # Admin might not have an employee profile, or might. For view tests, user identity is key.

    def test_employee_list_requires_login(self):
        response = self.client.get(reverse('payroll:employee_list')) # Assuming 'employee_list' is the name in urls.py
        self.assertEqual(response.status_code, 302) # Redirects to login
        # Assuming login URL is named 'users:login' based on previous similar contexts
        self.assertIn(reverse('users:login'), response.url)

    def test_employee_list_accessible_to_loggedin_user(self):
        self.client.login(email='testuser@example.com', password='password123')
        response = self.client.get(reverse('payroll:employee_list'))
        self.assertEqual(response.status_code, 200)

    def test_hr_dashboard_restricted_to_hr(self):
        # Test with non-HR user
        self.client.login(email='testuser@example.com', password='password123')
        response = self.client.get(reverse('payroll:hr_dashboard')) # Assuming name
        # For @user_passes_test, a failed test usually results in a redirect to login or a 403 if raise_exception=True
        # Default is redirect to login_url
        self.assertTrue(response.status_code == 302 or response.status_code == 403)
        if response.status_code == 302:
             self.assertIn(reverse('users:login'), response.url) # Check redirect URL

        # Test with HR user
        self.client.login(email='hruser@example.com', password='password123')
        response = self.client.get(reverse('payroll:hr_dashboard'))
        self.assertEqual(response.status_code, 200)

    def test_performance_reviews_list_restricted_to_hr(self): # This is for the 'performance_reviews' view
        self.client.login(email='testuser@example.com', password='password123')
        response = self.client.get(reverse('payroll:performance_reviews')) # Assuming name
        self.assertTrue(response.status_code == 302 or response.status_code == 403)
        if response.status_code == 302: # Check redirect if not a 403
            self.assertIn(reverse('users:login'), response.url)

        self.client.login(email='hruser@example.com', password='password123')
        response = self.client.get(reverse('payroll:performance_reviews'))
        self.assertEqual(response.status_code, 200)

    # Add more tests for other secured views like performance_review_detail, add_performance_review etc.
    # For views that require specific object permissions (e.g., viewing own performance review),
    # you'd need to create those objects (PerformanceReview) in setUp and test access.
    # Example for performance_review_detail (needs a review object):
    # def test_performance_review_detail_access(self):
    #     # Create a PerformanceReview instance for self.employee_profile
    #     # Ensure PerformanceReview model is imported: from payroll.models import PerformanceReview
    #     review = PerformanceReview.objects.create(employee=self.employee_profile, review_date='2023-01-01', rating=5, comments='Good')
    #
    #     # Test own access
    #     self.client.login(email='testuser@example.com', password='password123')
    #     response = self.client.get(reverse('payroll:performance_review_detail', args=[review.pk]))
    #     self.assertEqual(response.status_code, 200)
    #
    #     # Test other regular user access (should be forbidden)
    #     other_user = User.objects.create_user(email='other@example.com', password='password123')
    #     EmployeeProfile.objects.create(user=other_user, email=other_user.email, first_name='Other', last_name='Person') # Give them a profile
    #     self.client.login(email='other@example.com', password='password123')
    #     response = self.client.get(reverse('payroll:performance_review_detail', args=[review.pk]))
    #     self.assertEqual(response.status_code, 403) # HttpResponseForbidden
    #
    #     # Test HR access
    #     self.client.login(email='hruser@example.com', password='password123')
    #     response = self.client.get(reverse('payroll:performance_review_detail', args=[review.pk]))
    #     self.assertEqual(response.status_code, 200)
