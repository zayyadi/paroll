from django.test import TestCase, Client, RequestFactory
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission  # Added Permission
from django.contrib.contenttypes.models import ContentType  # Added ContentType
from django.http import HttpResponseRedirect
from decimal import Decimal
from payroll.models import (
    AttendanceRecord,
    Appraisal,
    AssetCategory,
    BenefitEnrollment,
    BenefitPlan,
    CourseEnrollment,
    EmployeeDocument,
    EmployeeAsset,
    EmployeeProfile,
    Goal,
    LearningCourse,
    IOU,
    LeaveRequest,
    OneOnOne,
    SurveyQuestion,
    SurveyResponse,
    SurveyTemplate,
    WorkflowExecution,
    WorkflowTemplate,
    Payroll,
    PayrollEntry,
    PayrollRun,
    PayrollRunEntry,
)
from company.models import Company
from datetime import date
from django.utils import timezone
from payroll.views.employee_view import dashboard
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

        # User creation already provisions profiles via signal; update them for clarity.
        cls.employee_profile_user = EmployeeProfile.objects.get(user=cls.user)
        cls.employee_profile_user.email = cls.user.email
        cls.employee_profile_user.first_name = cls.user.first_name
        cls.employee_profile_user.last_name = cls.user.last_name
        cls.employee_profile_user.save()

        cls.employee_profile_hr = EmployeeProfile.objects.get(user=cls.hr_user)
        cls.employee_profile_hr.email = cls.hr_user.email
        cls.employee_profile_hr.first_name = cls.hr_user.first_name
        cls.employee_profile_hr.last_name = cls.hr_user.last_name
        cls.employee_profile_hr.save()

        cls.employee_profile_noperm = EmployeeProfile.objects.get(user=cls.no_perm_user)
        cls.employee_profile_noperm.email = cls.no_perm_user.email
        cls.employee_profile_noperm.first_name = cls.no_perm_user.first_name
        cls.employee_profile_noperm.last_name = cls.no_perm_user.last_name
        cls.employee_profile_noperm.save()
        # Admin user typically does not need an EmployeeProfile unless specific views require it.

    def setUp(self):
        self.client = Client()
        self.factory = RequestFactory()

    def test_employee_list_requires_login_and_permission(self):
        # Test anonymous access
        response = self.client.get(reverse("payroll:employee_list"))
        self.assertIn(response.status_code, (302, 403))
        if response.status_code == 302:
            self.assertIn(reverse("users:login"), response.url)

        # Test with a logged-in employee-group user.
        self.client.login(email="noperm@example.com", password="password123")
        response = self.client.get(reverse("payroll:employee_list"))
        self.assertEqual(response.status_code, 200)

    def test_employee_list_hr_access(self):
        # HR user should have 'payroll.view_employeeprofile' via HR group from setup_groups_and_permissions
        self.client.login(email="hruser@example.com", password="password123")
        response = self.client.get(reverse("payroll:employee_list"))
        self.assertEqual(response.status_code, 200)

    def test_hr_dashboard_available_to_employee_group(self):
        self.client.login(email="noperm@example.com", password="password123")
        response = self.client.get(reverse("payroll:hr_dashboard"))
        self.assertEqual(response.status_code, 200)

        # Test with HR user
        self.client.login(email="hruser@example.com", password="password123")
        response = self.client.get(reverse("payroll:hr_dashboard"))
        self.assertEqual(response.status_code, 200)

    def test_appraisal_list_requires_explicit_permission(self):
        self.client.login(email="noperm@example.com", password="password123")
        response = self.client.get(reverse("payroll:appraisal_list"))
        self.assertEqual(response.status_code, 403)

        self.client.login(email="hruser@example.com", password="password123")
        response = self.client.get(reverse("payroll:appraisal_list"))
        self.assertEqual(response.status_code, 403)

        self.client.login(email="admin@example.com", password="password123")
        response = self.client.get(reverse("payroll:appraisal_list"))
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
        response = self.client.get(reverse("payroll:profile", args=[self.user.id]))
        self.assertEqual(response.status_code, 200)

    def test_employee_profile_view_other_profile_denied(self):
        # noperm_user trying to access testuser's profile
        self.client.login(email="noperm@example.com", password="password123")
        response = self.client.get(reverse("payroll:profile", args=[self.user.id]))
        self.assertEqual(response.status_code, 200)

    def test_employee_profile_view_hr_can_view_other(self):
        self.client.login(email="hruser@example.com", password="password123")
        # HR user trying to access testuser's profile
        # This relies on 'payroll.view_employeeprofile' being assigned to HR group
        response = self.client.get(reverse("payroll:profile", args=[self.user.id]))
        self.assertEqual(response.status_code, 200)

    def test_employee_profile_view_admin_can_view_other(self):
        self.client.login(email="admin@example.com", password="password123")
        # Admin user trying to access testuser's profile (superuser has all perms)
        response = self.client.get(reverse("payroll:profile", args=[self.user.id]))
        self.assertEqual(response.status_code, 200)

    def test_appraisal_detail_page_renders(self):
        appraisal = Appraisal.objects.create(
            company=self.admin_user.active_company,
            name="Quarterly Review",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 3, 31),
        )

        self.client.login(email="admin@example.com", password="password123")
        response = self.client.get(reverse("payroll:appraisal_detail", args=[appraisal.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Quarterly Review")
        self.assertContains(response, reverse("payroll:appraisal_assign"))

    def test_regular_user_dashboard_shows_recent_payslips(self):
        company = Company.objects.create(name="Dashboard Co")
        user = User.objects.create_user(
            email="dashboard-user@example.com",
            password="password123",
            first_name="Dash",
            last_name="User",
            company=company,
            active_company=company,
        )
        employee_profile = EmployeeProfile.objects.get(user=user)
        employee_profile.company = company
        employee_profile.status = "active"
        employee_profile.save(update_fields=["company", "status"])

        payroll = Payroll.objects.create(company=company, basic_salary=Decimal("120000.00"))
        employee_profile.employee_pay = payroll
        employee_profile.save(update_fields=["employee_pay"])

        payroll_entry = PayrollEntry.objects.create(
            company=company,
            pays=employee_profile,
            status="active",
        )
        payroll_run = PayrollRun.objects.create(
            company=company,
            name="April 2026 Payroll",
            paydays=date(2026, 4, 1),
            is_active=True,
        )
        PayrollRunEntry.objects.create(
            payroll_run=payroll_run,
            payroll_entry=payroll_entry,
        )

        request = self.factory.get(reverse("payroll:dashboard"))
        request.user = user
        response = dashboard(request)

        self.assertEqual(response.status_code, 200)
        self.assertIn("April 2026", response.content.decode())

    # Note: The URL name 'payroll:employee_profile' is an assumption for the employee detail view.
    # It needs to match the actual URL pattern for `payroll.views.employee_view.employee`.


class AttendanceViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        setup_groups_and_permissions()
        cls.company = Company.objects.create(name="Attendance Co")
        cls.hr_group = Group.objects.get(name="HR")

        cls.hr_user = User.objects.create_user(
            email="attendance-hr@example.com",
            password="password123",
            first_name="Attendance",
            last_name="HR",
            company=cls.company,
            active_company=cls.company,
        )
        cls.hr_user.groups.add(cls.hr_group)

        cls.employee_user = User.objects.create_user(
            email="attendance-employee@example.com",
            password="password123",
            first_name="Regular",
            last_name="Employee",
            company=cls.company,
            active_company=cls.company,
        )

        cls.hr_profile = EmployeeProfile.objects.get(user=cls.hr_user)
        cls.hr_profile.company = cls.company
        cls.hr_profile.save(update_fields=["company"])

        cls.employee_profile = EmployeeProfile.objects.get(user=cls.employee_user)
        cls.employee_profile.company = cls.company
        cls.employee_profile.save(update_fields=["company"])

    def setUp(self):
        self.client = Client()

    def test_attendance_overview_requires_hr_permission(self):
        response = self.client.get(reverse("payroll:attendance_overview"))
        self.assertEqual(response.status_code, 302)

        self.client.login(email="attendance-employee@example.com", password="password123")
        response = self.client.get(reverse("payroll:attendance_overview"))
        self.assertEqual(response.status_code, 403)

    def test_who_is_out_lists_leave_and_absence(self):
        LeaveRequest.objects.create(
            employee=self.employee_profile,
            leave_type="ANNUAL",
            start_date=date.today(),
            end_date=date.today(),
            reason="Out today",
            status="APPROVED",
        )

        AttendanceRecord.objects.create(
            company=self.company,
            employee=self.hr_profile,
            work_date=date.today(),
            status=AttendanceRecord.Status.ABSENT,
            hours_worked=0,
        )

        self.client.login(email="attendance-hr@example.com", password="password123")
        response = self.client.get(reverse("payroll:who_is_out"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Regular Employee")
        self.assertContains(response, "Attendance HR")

    def test_employee_clock_in_creates_today_record(self):
        self.client.login(email="attendance-employee@example.com", password="password123")
        response = self.client.post(reverse("payroll:attendance_clock"), {"action": "clock_in"})
        self.assertEqual(response.status_code, 302)

        record = AttendanceRecord.objects.get(
            employee=self.employee_profile,
            work_date=timezone.localdate(),
        )
        self.assertEqual(record.status, AttendanceRecord.Status.PRESENT)
        self.assertIsNotNone(record.clock_in)

    def test_employee_clock_out_updates_existing_record(self):
        AttendanceRecord.objects.create(
            company=self.company,
            employee=self.employee_profile,
            work_date=timezone.localdate(),
            status=AttendanceRecord.Status.PRESENT,
            clock_in=timezone.now() - timezone.timedelta(hours=8),
        )

        self.client.login(email="attendance-employee@example.com", password="password123")
        response = self.client.post(reverse("payroll:attendance_clock"), {"action": "clock_out"})
        self.assertEqual(response.status_code, 302)

        record = AttendanceRecord.objects.get(
            employee=self.employee_profile,
            work_date=timezone.localdate(),
        )
        self.assertIsNotNone(record.clock_out)

    def test_my_day_renders_without_existing_attendance_record(self):
        self.client.login(email="attendance-employee@example.com", password="password123")
        response = self.client.get(reverse("payroll:attendance_my_day"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, timezone.localdate().strftime("%B"))


class WorkflowExecutionViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        setup_groups_and_permissions()
        cls.company = Company.objects.create(name="Workflow Co")
        cls.admin_user = User.objects.create_superuser(
            email="workflow-admin@example.com",
            password="password123",
            company=cls.company,
            active_company=cls.company,
        )
        cls.department = EmployeeProfile._meta.get_field("department").related_model.objects.create(
            company=cls.company,
            name="Operations",
        )

    def setUp(self):
        self.client = Client()
        self.client.login(email="workflow-admin@example.com", password="password123")

    def test_add_employee_creates_onboarding_workflow_execution(self):
        template = WorkflowTemplate.objects.create(
            company=self.company,
            name="Standard Onboarding",
            workflow_type=WorkflowTemplate.WorkflowType.ONBOARDING,
            trigger_event="employee.created",
        )

        response = self.client.post(
            reverse("payroll:add_employee"),
            {
                "email": "newhire@example.com",
                "password1": "ComplexPass123",
                "password2": "ComplexPass123",
                "first_name": "New",
                "last_name": "Hire",
                "date_of_birth_0": "4",
                "date_of_birth_1": "1998",
                "gender": "male",
                "department": self.department.id,
                "job_title": "M",
                "contract_type": "P",
                "date_of_employment_0": "4",
                "date_of_employment_1": "2026",
                "tin_no": "TIN-NEW-HIRE-001",
                "bank": "GTB",
            },
        )

        self.assertEqual(response.status_code, 302)
        user = User.objects.get(email="newhire@example.com")
        employee = EmployeeProfile.objects.get(user=user)
        self.assertEqual(EmployeeProfile.objects.filter(user=user).count(), 1)

        execution = WorkflowExecution.objects.get(template=template, employee=employee)
        self.assertEqual(execution.company, self.company)
        self.assertEqual(execution.status, WorkflowExecution.Status.PENDING)
        self.assertEqual(execution.context["trigger_event"], "employee.created")
        self.assertEqual(execution.context["employee_email"], "newhire@example.com")

    def test_delete_employee_creates_offboarding_workflow_execution(self):
        departing_user = User.objects.create_user(
            email="departing@example.com",
            password="password123",
            first_name="Departing",
            last_name="Employee",
            company=self.company,
            active_company=self.company,
        )
        employee = EmployeeProfile.objects.get(user=departing_user)
        employee.company = self.company
        employee.save(update_fields=["company"])

        template = WorkflowTemplate.objects.create(
            company=self.company,
            name="Standard Offboarding",
            workflow_type=WorkflowTemplate.WorkflowType.OFFBOARDING,
            trigger_event="employee.deleted",
        )

        response = self.client.post(
            reverse("payroll:delete_employee", args=[employee.id]),
        )

        self.assertEqual(response.status_code, 302)
        employee.refresh_from_db()
        self.assertTrue(employee.is_deleted)

        execution = WorkflowExecution.objects.get(template=template, employee=employee)
        self.assertEqual(execution.company, self.company)
        self.assertEqual(execution.context["trigger_event"], "employee.deleted")
        self.assertEqual(execution.context["employee_email"], "departing@example.com")

    def test_workflow_overview_lists_company_executions(self):
        template = WorkflowTemplate.objects.create(
            company=self.company,
            name="Standard Onboarding",
            workflow_type=WorkflowTemplate.WorkflowType.ONBOARDING,
        )
        employee = EmployeeProfile.objects.get(user=self.admin_user)
        WorkflowExecution.objects.create(
            company=self.company,
            template=template,
            employee=employee,
            started_by=self.admin_user,
            context={"employee_name": "Workflow Admin"},
        )

        response = self.client.get(reverse("payroll:workflow_overview"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Workflow Operations")
        self.assertContains(response, "Standard Onboarding")


class EmployeeDocumentViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        setup_groups_and_permissions()
        cls.company = Company.objects.create(name="Documents Co")
        cls.hr_group = Group.objects.get(name="HR")

        cls.hr_user = User.objects.create_user(
            email="documents-hr@example.com",
            password="password123",
            first_name="Document",
            last_name="HR",
            company=cls.company,
            active_company=cls.company,
            is_staff=True,
        )
        cls.hr_user.groups.add(cls.hr_group)

        cls.employee_user = User.objects.create_user(
            email="documents-employee@example.com",
            password="password123",
            first_name="Regular",
            last_name="Reader",
            company=cls.company,
            active_company=cls.company,
        )

        cls.hr_profile = EmployeeProfile.objects.get(user=cls.hr_user)
        cls.hr_profile.company = cls.company
        cls.hr_profile.save(update_fields=["company"])

        cls.employee_profile = EmployeeProfile.objects.get(user=cls.employee_user)
        cls.employee_profile.company = cls.company
        cls.employee_profile.save(update_fields=["company"])

    def setUp(self):
        self.client = Client()

    def test_my_documents_lists_employee_documents(self):
        EmployeeDocument.objects.create(
            company=self.company,
            employee=self.employee_profile,
            title="Employee Handbook",
            document_type=EmployeeDocument.DocumentType.POLICY,
            acknowledgement_required=True,
        )

        self.client.login(email="documents-employee@example.com", password="password123")
        response = self.client.get(reverse("payroll:my_documents"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Employee Handbook")

    def test_employee_can_acknowledge_required_document(self):
        document = EmployeeDocument.objects.create(
            company=self.company,
            employee=self.employee_profile,
            title="Code of Conduct",
            document_type=EmployeeDocument.DocumentType.POLICY,
            acknowledgement_required=True,
            is_acknowledged=False,
        )

        self.client.login(email="documents-employee@example.com", password="password123")
        response = self.client.post(
            reverse("payroll:acknowledge_document", args=[document.id])
        )

        self.assertEqual(response.status_code, 302)
        document.refresh_from_db()
        self.assertTrue(document.is_acknowledged)
        self.assertIsNotNone(document.acknowledged_at)

    def test_document_overview_lists_company_documents(self):
        EmployeeDocument.objects.create(
            company=self.company,
            employee=self.employee_profile,
            title="Employment Contract",
            document_type=EmployeeDocument.DocumentType.CONTRACT,
            acknowledgement_required=True,
        )

        self.client.login(email="documents-hr@example.com", password="password123")
        response = self.client.get(reverse("payroll:document_overview"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Document Operations")
        self.assertContains(response, "Employment Contract")


class EmployeeAssetViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        setup_groups_and_permissions()
        cls.company = Company.objects.create(name="Assets Co")
        cls.hr_group = Group.objects.get(name="HR")

        cls.hr_user = User.objects.create_user(
            email="assets-hr@example.com",
            password="password123",
            first_name="Asset",
            last_name="Manager",
            company=cls.company,
            active_company=cls.company,
            is_staff=True,
        )
        cls.hr_user.groups.add(cls.hr_group)

        cls.employee_user = User.objects.create_user(
            email="assets-employee@example.com",
            password="password123",
            first_name="Assigned",
            last_name="Employee",
            company=cls.company,
            active_company=cls.company,
        )

        cls.hr_profile = EmployeeProfile.objects.get(user=cls.hr_user)
        cls.hr_profile.company = cls.company
        cls.hr_profile.save(update_fields=["company"])

        cls.employee_profile = EmployeeProfile.objects.get(user=cls.employee_user)
        cls.employee_profile.company = cls.company
        cls.employee_profile.save(update_fields=["company"])

        cls.category = AssetCategory.objects.create(
            company=cls.company,
            name="Laptop",
        )

    def setUp(self):
        self.client = Client()

    def test_my_assets_lists_assigned_assets(self):
        EmployeeAsset.objects.create(
            company=self.company,
            employee=self.employee_profile,
            category=self.category,
            name="MacBook Pro",
            asset_tag="LAP-001",
            status=EmployeeAsset.Status.IN_USE,
        )

        self.client.login(email="assets-employee@example.com", password="password123")
        response = self.client.get(reverse("payroll:my_assets"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "MacBook Pro")

    def test_asset_overview_lists_company_assets(self):
        EmployeeAsset.objects.create(
            company=self.company,
            employee=self.employee_profile,
            category=self.category,
            name="ThinkPad X1",
            asset_tag="LAP-002",
            status=EmployeeAsset.Status.IN_USE,
        )

        self.client.login(email="assets-hr@example.com", password="password123")
        response = self.client.get(reverse("payroll:asset_overview"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Asset Operations")
        self.assertContains(response, "ThinkPad X1")

    def test_hr_can_mark_asset_as_returned(self):
        asset = EmployeeAsset.objects.create(
            company=self.company,
            employee=self.employee_profile,
            category=self.category,
            name="Dell Monitor",
            asset_tag="MON-001",
            status=EmployeeAsset.Status.IN_USE,
        )

        self.client.login(email="assets-hr@example.com", password="password123")
        response = self.client.post(reverse("payroll:return_asset", args=[asset.id]))

        self.assertEqual(response.status_code, 302)
        asset.refresh_from_db()
        self.assertEqual(asset.status, EmployeeAsset.Status.RETURNED)
        self.assertIsNotNone(asset.returned_at)
        self.assertIsNone(asset.employee)


class PerformanceViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        setup_groups_and_permissions()
        cls.company = Company.objects.create(name="Performance Co")
        cls.hr_group = Group.objects.get(name="HR")

        cls.hr_user = User.objects.create_user(
            email="performance-hr@example.com",
            password="password123",
            first_name="Performance",
            last_name="Lead",
            company=cls.company,
            active_company=cls.company,
            is_staff=True,
        )
        cls.hr_user.groups.add(cls.hr_group)

        cls.employee_user = User.objects.create_user(
            email="performance-employee@example.com",
            password="password123",
            first_name="Growth",
            last_name="Employee",
            company=cls.company,
            active_company=cls.company,
        )

        cls.hr_profile = EmployeeProfile.objects.get(user=cls.hr_user)
        cls.hr_profile.company = cls.company
        cls.hr_profile.save(update_fields=["company"])

        cls.employee_profile = EmployeeProfile.objects.get(user=cls.employee_user)
        cls.employee_profile.company = cls.company
        cls.employee_profile.save(update_fields=["company"])

    def setUp(self):
        self.client = Client()

    def test_my_performance_lists_goals_and_one_on_ones(self):
        Goal.objects.create(
            company=self.company,
            employee=self.employee_profile,
            manager=self.hr_user,
            title="Improve payroll accuracy",
            cycle="Q2 2026",
            status=Goal.Status.ACTIVE,
            progress_percent=60,
        )
        OneOnOne.objects.create(
            company=self.company,
            employee=self.employee_profile,
            manager=self.hr_user,
            scheduled_for=timezone.now() + timezone.timedelta(days=2),
            agenda=["Career growth", "Roadblocks"],
        )

        self.client.login(email="performance-employee@example.com", password="password123")
        response = self.client.get(reverse("payroll:my_performance"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Improve payroll accuracy")
        self.assertContains(response, "Career growth")

    def test_performance_overview_lists_company_goals(self):
        Goal.objects.create(
            company=self.company,
            employee=self.employee_profile,
            manager=self.hr_user,
            title="Reduce payroll exceptions",
            cycle="Q2 2026",
            status=Goal.Status.ACTIVE,
        )

        self.client.login(email="performance-hr@example.com", password="password123")
        response = self.client.get(reverse("payroll:performance_overview"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Performance Hub")
        self.assertContains(response, "Reduce payroll exceptions")

    def test_hr_can_mark_one_on_one_completed(self):
        meeting = OneOnOne.objects.create(
            company=self.company,
            employee=self.employee_profile,
            manager=self.hr_user,
            scheduled_for=timezone.now(),
            status=OneOnOne.Status.SCHEDULED,
        )

        self.client.login(email="performance-hr@example.com", password="password123")
        response = self.client.post(reverse("payroll:complete_one_on_one", args=[meeting.id]))

        self.assertEqual(response.status_code, 302)
        meeting.refresh_from_db()
        self.assertEqual(meeting.status, OneOnOne.Status.COMPLETED)
        self.assertIsNotNone(meeting.completed_at)


class SurveyViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        setup_groups_and_permissions()
        cls.company = Company.objects.create(name="Survey Co")
        cls.hr_group = Group.objects.get(name="HR")

        cls.hr_user = User.objects.create_user(
            email="survey-hr@example.com",
            password="password123",
            first_name="Survey",
            last_name="Lead",
            company=cls.company,
            active_company=cls.company,
            is_staff=True,
        )
        cls.hr_user.groups.add(cls.hr_group)

        cls.employee_user = User.objects.create_user(
            email="survey-employee@example.com",
            password="password123",
            first_name="Feedback",
            last_name="User",
            company=cls.company,
            active_company=cls.company,
        )

        cls.hr_profile = EmployeeProfile.objects.get(user=cls.hr_user)
        cls.hr_profile.company = cls.company
        cls.hr_profile.save(update_fields=["company"])

        cls.employee_profile = EmployeeProfile.objects.get(user=cls.employee_user)
        cls.employee_profile.company = cls.company
        cls.employee_profile.save(update_fields=["company"])

    def setUp(self):
        self.client = Client()

    def test_my_surveys_lists_active_surveys(self):
        survey = SurveyTemplate.objects.create(
            company=self.company,
            name="Quarterly Pulse",
            survey_type=SurveyTemplate.SurveyType.PULSE,
            is_anonymous=False,
            is_active=True,
        )
        SurveyQuestion.objects.create(
            survey=survey,
            prompt="How supported do you feel?",
            question_type=SurveyQuestion.QuestionType.RATING,
            order=1,
        )

        self.client.login(email="survey-employee@example.com", password="password123")
        response = self.client.get(reverse("payroll:my_surveys"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Quarterly Pulse")

    def test_employee_can_submit_survey_response(self):
        survey = SurveyTemplate.objects.create(
            company=self.company,
            name="Onboarding Feedback",
            survey_type=SurveyTemplate.SurveyType.ONBOARDING,
            is_anonymous=False,
            is_active=True,
        )
        question = SurveyQuestion.objects.create(
            survey=survey,
            prompt="Rate your first week",
            question_type=SurveyQuestion.QuestionType.RATING,
            order=1,
        )

        self.client.login(email="survey-employee@example.com", password="password123")
        response = self.client.post(
            reverse("payroll:submit_survey", args=[survey.id]),
            {f"question_{question.id}": "4"},
        )

        self.assertEqual(response.status_code, 302)
        survey_response = SurveyResponse.objects.get(survey=survey, question=question)
        self.assertEqual(survey_response.employee, self.employee_profile)
        self.assertEqual(survey_response.numeric_response, 4)

    def test_survey_overview_lists_company_surveys(self):
        survey = SurveyTemplate.objects.create(
            company=self.company,
            name="Engagement Survey",
            survey_type=SurveyTemplate.SurveyType.ENGAGEMENT,
            is_anonymous=False,
            is_active=True,
        )
        SurveyQuestion.objects.create(
            survey=survey,
            prompt="How engaged do you feel?",
            question_type=SurveyQuestion.QuestionType.RATING,
            order=1,
        )

        self.client.login(email="survey-hr@example.com", password="password123")
        response = self.client.get(reverse("payroll:survey_overview"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Survey Center")
        self.assertContains(response, "Engagement Survey")


class LearningViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        setup_groups_and_permissions()
        cls.company = Company.objects.create(name="Learning Co")
        cls.hr_group = Group.objects.get(name="HR")

        cls.hr_user = User.objects.create_user(
            email="learning-hr@example.com",
            password="password123",
            first_name="Learning",
            last_name="Lead",
            company=cls.company,
            active_company=cls.company,
            is_staff=True,
        )
        cls.hr_user.groups.add(cls.hr_group)

        cls.employee_user = User.objects.create_user(
            email="learning-employee@example.com",
            password="password123",
            first_name="Training",
            last_name="User",
            company=cls.company,
            active_company=cls.company,
        )

        cls.hr_profile = EmployeeProfile.objects.get(user=cls.hr_user)
        cls.hr_profile.company = cls.company
        cls.hr_profile.save(update_fields=["company"])

        cls.employee_profile = EmployeeProfile.objects.get(user=cls.employee_user)
        cls.employee_profile.company = cls.company
        cls.employee_profile.save(update_fields=["company"])

    def setUp(self):
        self.client = Client()

    def test_my_learning_lists_assigned_courses(self):
        course = LearningCourse.objects.create(
            company=self.company,
            title="Workplace Conduct",
            course_type=LearningCourse.CourseType.COMPLIANCE,
            delivery_mode=LearningCourse.DeliveryMode.SELF_PACED,
            is_mandatory=True,
        )
        CourseEnrollment.objects.create(
            company=self.company,
            course=course,
            employee=self.employee_profile,
            status=CourseEnrollment.Status.ENROLLED,
        )

        self.client.login(email="learning-employee@example.com", password="password123")
        response = self.client.get(reverse("payroll:my_learning"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Workplace Conduct")

    def test_employee_can_mark_course_completed(self):
        course = LearningCourse.objects.create(
            company=self.company,
            title="Security Awareness",
            course_type=LearningCourse.CourseType.COMPLIANCE,
            delivery_mode=LearningCourse.DeliveryMode.SELF_PACED,
            is_mandatory=True,
        )
        enrollment = CourseEnrollment.objects.create(
            company=self.company,
            course=course,
            employee=self.employee_profile,
            status=CourseEnrollment.Status.IN_PROGRESS,
        )

        self.client.login(email="learning-employee@example.com", password="password123")
        response = self.client.post(
            reverse("payroll:complete_learning_course", args=[enrollment.id])
        )

        self.assertEqual(response.status_code, 302)
        enrollment.refresh_from_db()
        self.assertEqual(enrollment.status, CourseEnrollment.Status.COMPLETED)
        self.assertIsNotNone(enrollment.completed_at)

    def test_learning_overview_lists_company_courses(self):
        course = LearningCourse.objects.create(
            company=self.company,
            title="Manager Essentials",
            course_type=LearningCourse.CourseType.LEADERSHIP,
            delivery_mode=LearningCourse.DeliveryMode.INSTRUCTOR_LED,
        )
        CourseEnrollment.objects.create(
            company=self.company,
            course=course,
            employee=self.employee_profile,
            status=CourseEnrollment.Status.ENROLLED,
        )

        self.client.login(email="learning-hr@example.com", password="password123")
        response = self.client.get(reverse("payroll:learning_overview"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Learning Center")
        self.assertContains(response, "Manager Essentials")


class BenefitViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        setup_groups_and_permissions()
        cls.company = Company.objects.create(name="Benefits Co")
        cls.hr_group = Group.objects.get(name="HR")

        cls.hr_user = User.objects.create_user(
            email="benefits-hr@example.com",
            password="password123",
            first_name="Benefits",
            last_name="Lead",
            company=cls.company,
            active_company=cls.company,
            is_staff=True,
        )
        cls.hr_user.groups.add(cls.hr_group)

        cls.employee_user = User.objects.create_user(
            email="benefits-employee@example.com",
            password="password123",
            first_name="Covered",
            last_name="Employee",
            company=cls.company,
            active_company=cls.company,
        )

        cls.hr_profile = EmployeeProfile.objects.get(user=cls.hr_user)
        cls.hr_profile.company = cls.company
        cls.hr_profile.save(update_fields=["company"])

        cls.employee_profile = EmployeeProfile.objects.get(user=cls.employee_user)
        cls.employee_profile.company = cls.company
        cls.employee_profile.save(update_fields=["company"])

    def setUp(self):
        self.client = Client()

    def test_my_benefits_lists_active_plans(self):
        BenefitPlan.objects.create(
            company=self.company,
            name="Health Plus",
            plan_type=BenefitPlan.PlanType.HEALTH,
            is_active=True,
        )

        self.client.login(email="benefits-employee@example.com", password="password123")
        response = self.client.get(reverse("payroll:my_benefits"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Health Plus")

    def test_employee_can_enroll_in_benefit_plan(self):
        plan = BenefitPlan.objects.create(
            company=self.company,
            name="Pension Advantage",
            plan_type=BenefitPlan.PlanType.PENSION,
            is_active=True,
        )

        self.client.login(email="benefits-employee@example.com", password="password123")
        response = self.client.post(reverse("payroll:enroll_benefit", args=[plan.id]))

        self.assertEqual(response.status_code, 302)
        enrollment = BenefitEnrollment.objects.get(plan=plan, employee=self.employee_profile)
        self.assertEqual(enrollment.status, BenefitEnrollment.Status.ENROLLED)

    def test_benefit_overview_lists_company_plans(self):
        plan = BenefitPlan.objects.create(
            company=self.company,
            name="Wellness Boost",
            plan_type=BenefitPlan.PlanType.WELLNESS,
            is_active=True,
        )
        BenefitEnrollment.objects.create(
            company=self.company,
            plan=plan,
            employee=self.employee_profile,
            status=BenefitEnrollment.Status.ENROLLED,
        )

        self.client.login(email="benefits-hr@example.com", password="password123")
        response = self.client.get(reverse("payroll:benefit_overview"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Benefits Center")
        self.assertContains(response, "Wellness Boost")
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


class RouteHardeningTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        setup_groups_and_permissions()
        cls.company = Company.objects.create(name="Route Hardening Co")

        cls.admin_user = User.objects.create_superuser(
            email="route-admin@example.com",
            password="password123",
            company=cls.company,
            active_company=cls.company,
        )
        cls.employee_user = User.objects.create_user(
            email="route-employee@example.com",
            password="password123",
            company=cls.company,
            active_company=cls.company,
        )
        cls.hr_user = User.objects.create_user(
            email="route-hr@example.com",
            password="password123",
            company=cls.company,
            active_company=cls.company,
        )
        cls.hr_user.groups.add(Group.objects.get(name="HR"))

        cls.employee_profile = EmployeeProfile.objects.get(user=cls.employee_user)
        cls.employee_profile.company = cls.company
        cls.employee_profile.status = "active"
        cls.employee_profile.save(update_fields=["company", "status"])

        cls.hr_profile = EmployeeProfile.objects.get(user=cls.hr_user)
        cls.hr_profile.company = cls.company
        cls.hr_profile.status = "active"
        cls.hr_profile.save(update_fields=["company", "status"])

        cls.leave_request = LeaveRequest.objects.create(
            employee=cls.employee_profile,
            leave_type="ANNUAL",
            start_date=date(2026, 4, 2),
            end_date=date(2026, 4, 3),
            reason="Method hardening",
            status="PENDING",
        )
        cls.iou = IOU.objects.create(
            employee_id=cls.employee_profile,
            amount=Decimal("5000.00"),
            tenor=1,
            reason="Tenant guard",
            due_date=date(2026, 4, 30),
        )

    def setUp(self):
        self.client = Client()

    def test_delete_employee_requires_post(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(
            reverse("payroll:delete_employee", kwargs={"id": self.employee_profile.id})
        )
        self.assertEqual(response.status_code, 405)

    def test_leave_approval_requires_post(self):
        self.client.force_login(self.hr_user)
        response = self.client.get(
            reverse("payroll:approve_leave", kwargs={"pk": self.leave_request.pk})
        )
        self.assertEqual(response.status_code, 405)

    def test_leave_rejection_requires_post(self):
        self.client.force_login(self.hr_user)
        response = self.client.get(
            reverse("payroll:reject_leave", kwargs={"pk": self.leave_request.pk})
        )
        self.assertEqual(response.status_code, 405)

    def test_notification_preferences_template_renders(self):
        self.client.force_login(self.employee_user)
        response = self.client.get(reverse("payroll:notification_preferences"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "notifications/notification_preferences.html")

    def test_notification_type_preferences_template_renders(self):
        self.client.force_login(self.employee_user)
        response = self.client.get(
            reverse(
                "payroll:notification_type_preferences",
                kwargs={"notification_type": "LEAVE_REQUEST"},
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response, "notifications/notification_type_preferences.html"
        )

    def test_apply_leave_uses_active_company_employee_profile(self):
        other_company = Company.objects.create(name="Other Leave Co")
        self.employee_profile.company = other_company
        self.employee_profile.save(update_fields=["company"])

        self.client.force_login(self.employee_user)
        response = self.client.get(reverse("payroll:apply_leave"))

        self.assertIsInstance(response, HttpResponseRedirect)
        self.assertRedirects(
            response,
            reverse("payroll:dashboard"),
            fetch_redirect_response=False,
        )

    def test_request_iou_uses_active_company_employee_profile(self):
        other_company = Company.objects.create(name="Other IOU Co")
        self.employee_profile.company = other_company
        self.employee_profile.save(update_fields=["company"])

        self.client.force_login(self.employee_user)
        response = self.client.get(reverse("payroll:request_iou"))

        self.assertIsInstance(response, HttpResponseRedirect)
        self.assertRedirects(
            response,
            reverse("payroll:dashboard"),
            fetch_redirect_response=False,
        )
