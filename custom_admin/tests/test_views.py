from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from payroll.models.employee_profile import Department, EmployeeProfile
# from payroll.models.payroll import Payroll # For EmployeeProfile.employee_pay if needed by tests
# from monthyear import Month # If setting MonthField directly

User = get_user_model()

def create_test_user(username, password="password123", is_staff=False, is_superuser=False, email_suffix="@example.com", **kwargs):
    email = kwargs.pop('email', f"{username}{email_suffix}")
    # Ensure first_name and last_name are provided if not in kwargs, to avoid issues with signals or model fields
    kwargs.setdefault('first_name', username.capitalize())
    kwargs.setdefault('last_name', "User")
    user = User.objects.create_user(username=username, password=password, email=email, **kwargs)
    user.is_staff = is_staff
    user.is_superuser = is_superuser
    user.save()
    return user

def create_test_department(name="Test Department", description="Test Description"):
    # This will get the department if it exists, or create it if it doesn't.
    # Useful if multiple tests might try to create the same department.
    department, created = Department.objects.get_or_create(
        name=name, 
        defaults={'description': description}
    )
    # If it already existed and you want to ensure the description is updated:
    if not created and department.description != description:
        department.description = description
        department.save()
    return department

def create_test_employee_profile(user, department=None, **kwargs):
    # The signal create_employee_profile in payroll.models.employee_profile 
    # automatically creates an EmployeeProfile when a CustomUser is created.
    
    # Try to get the profile created by the signal first
    try:
        profile = EmployeeProfile.objects.get(user=user)
    except EmployeeProfile.DoesNotExist:
        # This case indicates the signal might not have run or the profile was deleted.
        # update_or_create will handle creating it.
        profile = None # Explicitly set to None if not found

    # Define defaults for fields we want to ensure are set for tests
    # (especially if not set by signal or if we want specific test values)
    defaults = {
        'first_name': kwargs.pop('first_name', user.first_name if user.first_name else user.username),
        'last_name': kwargs.pop('last_name', user.last_name if user.last_name else "User"),
        'email': kwargs.pop('email', user.email), # Use user's email by default
        'department': department or Department.objects.get_or_create(name=f"Default Test Dept for {user.username}")[0],
        'job_title': kwargs.pop('job_title', 'CASUAL'), # Assuming 'CASUAL' is a valid choice key
        'pension_rsa': kwargs.pop('pension_rsa', f"RSA-TEST-{user.username[:10]}{user.pk}{EmployeeProfile.objects.count() + 1}"), # Attempt at uniqueness
        'status': kwargs.pop('status', 'active'), # Default to 'active' for test usability
        # 'date_of_birth': Month(year=1990, month=1), # Example
        # 'date_of_employment': Month(year=2020, month=1), # Example
        # employee_pay (ForeignKey to Payroll) is nullable/blank, can be omitted or set in kwargs
    }
    
    # Merge provided kwargs, overriding defaults
    for key, value in kwargs.items():
        defaults[key] = value

    # Use update_or_create to handle both existing (signal-created) and potentially missing profiles
    # It's crucial that 'user' is the unique identifier for matching.
    profile, created = EmployeeProfile.objects.update_or_create(
        user=user,
        defaults=defaults
    )
    return profile

class CustomAdminAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff_user = create_test_user(username='stafftester', is_staff=True, first_name="Staff", last_name="User")
        cls.non_staff_user = create_test_user(username='normaltester', first_name="Normal", last_name="User")
        cls.dashboard_url = reverse('custom_admin:dashboard')
        # Assuming EmployeeProfile is registered under app_label 'payroll' and model_name 'employeeprofile'
        # and specific URL payroll_employeeprofile_list exists.
        cls.employee_list_url = reverse('custom_admin:payroll_employeeprofile_list')

    def setUp(self):
        self.client = Client()

    # Dashboard Access Tests
    def test_dashboard_anonymous_redirects_to_login(self):
        self.client.logout() # Ensure no one is logged in
        response = self.client.get(self.dashboard_url)
        # Assuming LOGIN_URL is 'users:login' as per project settings
        expected_redirect_url = f"{reverse('users:login')}?next={self.dashboard_url}"
        self.assertRedirects(response, expected_redirect_url)

    def test_dashboard_non_staff_forbidden(self):
        self.client.login(username=self.non_staff_user.username, password='password123')
        response = self.client.get(self.dashboard_url)
        self.assertEqual(response.status_code, 403) # Forbidden

    def test_dashboard_staff_accessible(self):
        self.client.login(username=self.staff_user.username, password='password123')
        response = self.client.get(self.dashboard_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'custom_admin/dashboard.html')

    # Generic List View Access Tests (using EmployeeProfile list as an example)
    def test_model_list_anonymous_redirects_to_login(self):
        self.client.logout()
        response = self.client.get(self.employee_list_url)
        expected_redirect_url = f"{reverse('users:login')}?next={self.employee_list_url}"
        self.assertRedirects(response, expected_redirect_url)

    def test_model_list_non_staff_forbidden(self):
        self.client.login(username=self.non_staff_user.username, password='password123')
        response = self.client.get(self.employee_list_url)
        self.assertEqual(response.status_code, 403)

    def test_model_list_staff_accessible(self):
        self.client.login(username=self.staff_user.username, password='password123')
        response = self.client.get(self.employee_list_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'custom_admin/generic_list.html')

class EmployeeProfileAdminCrudTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff_user = create_test_user(username='crud_staff', is_staff=True, first_name="Staff", last_name="Admin")
        
        cls.dept_hr = create_test_department(name="Human Resources")
        cls.dept_eng = create_test_department(name="Engineering")

        # User for emp1
        cls.user_emp1 = create_test_user(username='emp1', first_name="Alice", last_name="Smith", email="alice@example.com")
        cls.emp1 = create_test_employee_profile(
            user=cls.user_emp1, department=cls.dept_hr, 
            job_title='MANAGER', status='active', 
            pension_rsa="RSAEMP1", gender='FEMALE' # Added gender
        )

        # User for emp2
        cls.user_emp2 = create_test_user(username='emp2', first_name="Bob", last_name="Johnson", email="bob@example.com")
        cls.emp2 = create_test_employee_profile(
            user=cls.user_emp2, department=cls.dept_eng,
            job_title='STAFF', status='pending', 
            pension_rsa="RSAEMP2", gender='MALE' # Added gender
        )
        
        cls.list_url = reverse('custom_admin:payroll_employeeprofile_list')
        cls.create_url = reverse('custom_admin:payroll_employeeprofile_create')

    def setUp(self):
        self.client = Client()
        self.client.login(username=self.staff_user.username, password='password123')

    # List View Tests
    def test_list_view_displays_employees(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.emp1.first_name)
        self.assertContains(response, self.emp2.last_name)
        # Convert object_list to a list of pks for easier comparison if order is not guaranteed
        object_pks_in_context = [obj.pk for obj in response.context['object_list']]
        self.assertIn(self.emp1.pk, object_pks_in_context)
        self.assertIn(self.emp2.pk, object_pks_in_context)


    def test_list_view_search_first_name(self):
        response = self.client.get(self.list_url, {'q': 'Alice'})
        self.assertContains(response, self.emp1.first_name)
        self.assertNotContains(response, self.emp2.first_name)

    def test_list_view_filter_status(self):
        response = self.client.get(self.list_url, {'status': 'active'})
        self.assertContains(response, self.emp1.first_name)
        self.assertNotContains(response, self.emp2.first_name)
    
    def test_list_view_filter_department(self):
        response = self.client.get(self.list_url, {'department': self.dept_hr.id})
        self.assertContains(response, self.emp1.first_name)
        self.assertNotContains(response, self.emp2.first_name)

    # Create View Tests
    def test_create_view_get_renders_form(self):
        response = self.client.get(self.create_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'custom_admin/generic_form.html')

    def test_create_view_post_valid(self):
        # The EmployeeProfile model's 'user' field is OneToOne, nullable and blank.
        # The current EmployeeProfileCreateView does not include 'user' in its 'fields'.
        # This means when we POST to create an EmployeeProfile, it will be created without a user.
        # This is generally not desired but tests the view as currently defined.
        initial_count = EmployeeProfile.objects.count()
        form_data = {
            'first_name': "TestCreate", 'last_name': "UserCreate", 'email': "testcreate@example.com",
            'department': self.dept_eng.id, 'job_title': 'STAFF', 'status': 'active',
            'pension_rsa': 'RSA-CREATE-VALID', 'gender': 'MALE',
            'phone': '1234567890', 'address': '123 Test St',
            # 'employee_pay' is nullable; 'bank', 'bank_account_name', 'bank_account_number' are nullable
            # 'emergency_contact_name', etc. are nullable
        }
        response = self.client.post(self.create_url, data=form_data)
        
        # Check for redirect to list_url on success
        self.assertRedirects(response, self.list_url, msg_prefix=f"Form errors: {response.context.get('form').errors if response.context else 'No form context'}")
        self.assertEqual(EmployeeProfile.objects.count(), initial_count + 1)
        self.assertTrue(EmployeeProfile.objects.filter(email="testcreate@example.com", pension_rsa='RSA-CREATE-VALID').exists())


    def test_create_view_post_invalid_missing_required(self):
        initial_count = EmployeeProfile.objects.count()
        # Missing required fields like first_name, last_name, email, pension_rsa, gender, etc.
        form_data = {'department': self.dept_eng.id, 'status': 'active'} 
        response = self.client.post(self.create_url, data=form_data)
        self.assertEqual(response.status_code, 200) # Re-renders form
        self.assertTrue(response.context['form'].errors)
        self.assertIn('first_name', response.context['form'].errors) # Example check
        self.assertEqual(EmployeeProfile.objects.count(), initial_count)

    # Update View Tests
    def test_update_view_get_renders_form_with_instance_data(self):
        update_url = reverse('custom_admin:payroll_employeeprofile_update', kwargs={'pk': self.emp1.pk})
        response = self.client.get(update_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.emp1.first_name)
        self.assertTemplateUsed(response, 'custom_admin/generic_form.html')

    def test_update_view_post_valid(self):
        update_url = reverse('custom_admin:payroll_employeeprofile_update', kwargs={'pk': self.emp1.pk})
        updated_first_name = "AliciaUpdated"
        # Construct form_data with all fields required by the form
        # Fields for EmployeeProfileUpdateView:
        # ['first_name', 'last_name', 'email', 'department', 'job_title', 'contract_type', 
        #  'date_of_employment', 'date_of_birth', 'gender', 'phone', 'address', 'employee_pay', 
        #  'pension_rsa', 'bank', 'bank_account_name', 'bank_account_number', 'photo', 
        #  'emergency_contact_name', 'emergency_contact_relationship', 'emergency_contact_phone', 
        #  'next_of_kin_name', 'next_of_kin_relationship', 'next_of_kin_phone', 'status']
        form_data = {
            'first_name': updated_first_name, 
            'last_name': self.emp1.last_name, 
            'email': self.emp1.email, 
            'department': self.emp1.department.id, 
            'job_title': self.emp1.job_title, 
            'status': self.emp1.status,
            'pension_rsa': self.emp1.pension_rsa, 
            'gender': self.emp1.gender,
            'phone': self.emp1.phone or '', # Ensure required fields have values
            'address': self.emp1.address or '',
            'contract_type': self.emp1.contract_type or '', # Assuming it can be blank or has a default
            # Nullable ForeignKey/OneToOne fields can be omitted if they are None
            'employee_pay': self.emp1.employee_pay.id if self.emp1.employee_pay else '',
            'bank': self.emp1.bank.id if self.emp1.bank else '',
            'bank_account_name': self.emp1.bank_account_name or '',
            'bank_account_number': self.emp1.bank_account_number or '',
            'emergency_contact_name': self.emp1.emergency_contact_name or '',
            'emergency_contact_relationship': self.emp1.emergency_contact_relationship or '',
            'emergency_contact_phone': self.emp1.emergency_contact_phone or '',
            'next_of_kin_name': self.emp1.next_of_kin_name or '',
            'next_of_kin_relationship': self.emp1.next_of_kin_relationship or '',
            'next_of_kin_phone': self.emp1.next_of_kin_phone or '',
            # Date fields (date_of_employment, date_of_birth) use MonthSelectorWidget
            # They are submitted as two parts: field_0 (month), field_1 (year)
            'date_of_employment_0': self.emp1.date_of_employment.month if self.emp1.date_of_employment else '',
            'date_of_employment_1': self.emp1.date_of_employment.year if self.emp1.date_of_employment else '',
            'date_of_birth_0': self.emp1.date_of_birth.month if self.emp1.date_of_birth else '',
            'date_of_birth_1': self.emp1.date_of_birth.year if self.emp1.date_of_birth else '',
        }
        # Photo field is FileInput, not including it in POST data unless testing file upload
        
        response = self.client.post(update_url, data=form_data)
        self.assertRedirects(response, self.list_url, msg_prefix=f"Form errors: {response.context.get('form').errors if response.context else 'No form context'}")
        self.emp1.refresh_from_db()
        self.assertEqual(self.emp1.first_name, updated_first_name)

    # Delete View Tests
    def test_delete_view_get_renders_confirmation(self):
        delete_url = reverse('custom_admin:payroll_employeeprofile_delete', kwargs={'pk': self.emp1.pk})
        response = self.client.get(delete_url)
        self.assertEqual(response.status_code, 200)
        # Check for a unique part of the confirmation message
        self.assertContains(response, f"Are you sure you want to delete the Employee Profile titled: &quot;{str(self.emp1)}&quot;?")
        self.assertTemplateUsed(response, 'custom_admin/generic_confirm_delete.html')

    def test_delete_view_post_deletes_employee_profile(self): # Renamed for clarity
        # Create a new user and profile specifically for this delete test to avoid impacting other tests
        user_to_delete = create_test_user(username='todelete', first_name="ToDelete", last_name="User")
        profile_to_delete = create_test_employee_profile(
            user=user_to_delete, department=self.dept_hr, pension_rsa="RSATODELETE", gender='OTHER'
        )
        delete_url = reverse('custom_admin:payroll_employeeprofile_delete', kwargs={'pk': profile_to_delete.pk})
        initial_count = EmployeeProfile.objects.count()
        
        response = self.client.post(delete_url) # POST to confirm deletion
        self.assertRedirects(response, self.list_url)
        self.assertEqual(EmployeeProfile.objects.count(), initial_count - 1)
        self.assertFalse(EmployeeProfile.objects.filter(pk=profile_to_delete.pk).exists())
        # Optionally, check if the associated user is also deleted, depending on model's on_delete behavior for user.
        # EmployeeProfile.user is OneToOneField(User, on_delete=models.CASCADE), so user should be deleted too.
        self.assertFalse(User.objects.filter(pk=user_to_delete.pk).exists())

from datetime import date, timedelta
from payroll.models.payroll import LeaveRequest, LeavePolicy
from django.contrib.messages import get_messages

class LeaveRequestAdminActionsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff_user = create_test_user(username='action_staff', is_staff=True)
        
        user1 = create_test_user(username='emp_leave1')
        cls.emp_profile1 = create_test_employee_profile(user=user1, first_name="LeaveEmp1")
        
        user2 = create_test_user(username='emp_leave2')
        cls.emp_profile2 = create_test_employee_profile(user=user2, first_name="LeaveEmp2")

        # Ensure choices for LeavePolicy.leave_type are valid. Assuming 'ANNUAL' and 'SICK' are.
        # If LeavePolicy has unique constraints on leave_type, get_or_create is good.
        cls.annual_policy, _ = LeavePolicy.objects.get_or_create(leave_type='ANNUAL', defaults={'max_days': 20})
        cls.sick_policy, _ = LeavePolicy.objects.get_or_create(leave_type='SICK', defaults={'max_days': 10})

        cls.list_url = reverse('custom_admin:payroll_leaverequest_list')

    def setUp(self):
        self.client = Client()
        self.client.login(username=self.staff_user.username, password='password123')

        # Create fresh objects for each test to ensure independence
        self.lr_pending1 = LeaveRequest.objects.create(
            employee=self.emp_profile1, leave_type=self.annual_policy,
            start_date=date.today(), end_date=date.today() + timedelta(days=2),
            reason="Vacation Test 1", status="PENDING"
        )
        self.lr_pending2 = LeaveRequest.objects.create(
            employee=self.emp_profile2, leave_type=self.sick_policy,
            start_date=date.today(), end_date=date.today() + timedelta(days=1),
            reason="Sick Test 1", status="PENDING"
        )
        self.lr_already_approved = LeaveRequest.objects.create(
            employee=self.emp_profile1, leave_type=self.annual_policy,
            start_date=date.today() + timedelta(days=5), end_date=date.today() + timedelta(days=7),
            reason="Already Approved LR", status="APPROVED"
        )

    def test_approve_selected_pending_leave_requests(self):
        response = self.client.post(self.list_url, {
            'action': 'approve_selected',
            'selected_ids': [self.lr_pending1.pk, self.lr_pending2.pk]
        })
        self.assertEqual(response.status_code, 302) # Should redirect
        self.lr_pending1.refresh_from_db()
        self.lr_pending2.refresh_from_db()
        self.assertEqual(self.lr_pending1.status, 'APPROVED')
        self.assertEqual(self.lr_pending2.status, 'APPROVED')
        
        messages_list = list(get_messages(response.wsgi_request))
        self.assertTrue(any("Successfully performed action" in str(m) for m in messages_list))
        self.assertTrue(any("on 2 item(s)" in str(m) for m in messages_list))


    def test_reject_selected_pending_leave_requests(self):
        response = self.client.post(self.list_url, {
            'action': 'reject_selected',
            'selected_ids': [self.lr_pending1.pk, self.lr_pending2.pk]
        })
        self.assertEqual(response.status_code, 302)
        self.lr_pending1.refresh_from_db()
        self.lr_pending2.refresh_from_db()
        self.assertEqual(self.lr_pending1.status, 'REJECTED')
        self.assertEqual(self.lr_pending2.status, 'REJECTED')

        messages_list = list(get_messages(response.wsgi_request))
        self.assertTrue(any("Successfully performed action" in str(m) for m in messages_list))
        self.assertTrue(any("on 2 item(s)" in str(m) for m in messages_list))

    def test_action_skips_non_pending_requests_for_approval(self):
        response = self.client.post(self.list_url, {
            'action': 'approve_selected',
            'selected_ids': [self.lr_pending1.pk, self.lr_already_approved.pk]
        })
        self.assertEqual(response.status_code, 302)
        self.lr_pending1.refresh_from_db()
        self.lr_already_approved.refresh_from_db()
        self.assertEqual(self.lr_pending1.status, 'APPROVED') 
        self.assertEqual(self.lr_already_approved.status, 'APPROVED') 
        
        messages_list = list(get_messages(response.wsgi_request))
        self.assertTrue(any("1 selected item(s) were not in a state to be approved" in str(m) for m in messages_list))
        self.assertTrue(any("Successfully performed action" in str(m) and "on 1 item(s)" in str(m) for m in messages_list))


    def test_action_no_action_selected(self):
        response = self.client.post(self.list_url, {'selected_ids': [self.lr_pending1.pk]})
        self.assertEqual(response.status_code, 302) 
        messages_list = list(get_messages(response.wsgi_request))
        self.assertTrue(any("No action was selected" in str(m) for m in messages_list))
        self.lr_pending1.refresh_from_db()
        self.assertEqual(self.lr_pending1.status, 'PENDING') 

    def test_action_no_items_selected(self):
        response = self.client.post(self.list_url, {'action': 'approve_selected'})
        self.assertEqual(response.status_code, 302) 
        messages_list = list(get_messages(response.wsgi_request))
        self.assertTrue(any("No items were selected" in str(m) for m in messages_list))
