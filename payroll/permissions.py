from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from users.models import CustomUser
from payroll.models import ( # Assuming all these models are in payroll.models directly or available via __init__.py
    LeaveRequest, LeavePolicy, EmployeeProfile, Payroll, IOU,
    PerformanceReview, Allowance, Deduction, PayT, AuditTrail
    # PayVar might also be relevant depending on how payroll is managed
)

# It's good practice to wrap this in a function to be called by a post_migrate signal or manually
def setup_groups_and_permissions():
    print("Setting up default groups and permissions...")

    # Create groups
    super_admin_group, _ = Group.objects.get_or_create(name='Super Admin')
    admin_group, _ = Group.objects.get_or_create(name='Admin')
    hr_group, _ = Group.objects.get_or_create(name='HR')
    supervisor_group, _ = Group.objects.get_or_create(name='Supervisor')
    employee_group, _ = Group.objects.get_or_create(name='Employee')

    # Assign permissions to groups

    # Super Admin - Gets all permissions
    super_admin_group.permissions.set(Permission.objects.all())
    print(f"Configured Super Admin group with all permissions.")

    # Admin Group
    admin_permissions_list = []
    try:
        user_ct = ContentType.objects.get_for_model(CustomUser)
        admin_permissions_list.extend(
            Permission.objects.filter(content_type=user_ct, codename__in=['view_customuser', 'change_customuser', 'add_customuser', 'delete_customuser'])
        )
    except ContentType.DoesNotExist:
        print("Warning: ContentType for CustomUser not found. Skipping CustomUser admin permissions.")

    payroll_models_for_admin = {
        LeaveRequest: ['add_leaverequest', 'change_leaverequest', 'delete_leaverequest', 'view_leaverequest'],
        LeavePolicy: ['add_leavepolicy', 'change_leavepolicy', 'delete_leavepolicy', 'view_leavepolicy'],
        EmployeeProfile: ['add_employeeprofile', 'change_employeeprofile', 'delete_employeeprofile', 'view_employeeprofile'],
        Payroll: ['add_payroll', 'change_payroll', 'delete_payroll', 'view_payroll'],
        PayT: ['add_payt', 'change_payt', 'delete_payt', 'view_payt'],
        IOU: ['add_iou', 'change_iou', 'delete_iou', 'view_iou'],
        Allowance: ['add_allowance', 'change_allowance', 'delete_allowance', 'view_allowance'],
        Deduction: ['add_deduction', 'change_deduction', 'delete_deduction', 'view_deduction'],
        PerformanceReview: ['add_performancereview', 'change_performancereview', 'delete_performancereview', 'view_performancereview'],
        AuditTrail: ['view_audittrail'],
    }
    for model, codenames in payroll_models_for_admin.items():
        try:
            ct = ContentType.objects.get_for_model(model)
            admin_permissions_list.extend(Permission.objects.filter(content_type=ct, codename__in=codenames))
        except ContentType.DoesNotExist:
            print(f"Warning: ContentType for {model.__name__} not found. Skipping its admin permissions.")
    admin_group.permissions.set(admin_permissions_list)
    print(f"Configured Admin group with {len(admin_permissions_list)} permissions.")


    # HR Group
    hr_permissions_list = []
    try:
        user_ct = ContentType.objects.get_for_model(CustomUser)
        # HR typically views users, may not add/change/delete them directly if Admin does that.
        hr_permissions_list.extend(Permission.objects.filter(content_type=user_ct, codename__in=['view_customuser', 'change_customuser']))
    except ContentType.DoesNotExist:
        print("Warning: ContentType for CustomUser not found. Skipping CustomUser HR permissions.")

    payroll_models_for_hr = {
        LeaveRequest: ['add_leaverequest', 'change_leaverequest', 'view_leaverequest', 'delete_leaverequest'], # Full leave mgt
        LeavePolicy: ['add_leavepolicy', 'change_leavepolicy', 'delete_leavepolicy', 'view_leavepolicy'], # Full policy mgt
        EmployeeProfile: ['add_employeeprofile', 'change_employeeprofile', 'view_employeeprofile', 'delete_employeeprofile'], # Full employee mgt
        PerformanceReview: ['add_performancereview', 'change_performancereview', 'view_performancereview', 'delete_performancereview'],
        IOU: ['add_iou', 'change_iou', 'delete_iou', 'view_iou'], # HR might manage IOUs fully
        Payroll: ['view_payroll', 'change_payroll'], # HR can view and adjust payroll
        PayT: ['view_payt', 'change_payt'], # HR can view and adjust pay periods
        Allowance: ['add_allowance', 'change_allowance', 'delete_allowance', 'view_allowance'], # HR manages allowances
        Deduction: ['add_deduction', 'change_deduction', 'delete_deduction', 'view_deduction'], # HR manages deductions
    }
    for model, codenames in payroll_models_for_hr.items():
        try:
            ct = ContentType.objects.get_for_model(model)
            hr_permissions_list.extend(Permission.objects.filter(content_type=ct, codename__in=codenames))
        except ContentType.DoesNotExist:
            print(f"Warning: ContentType for {model.__name__} not found. Skipping its HR permissions.")
    hr_group.permissions.set(hr_permissions_list)
    print(f"Configured HR group with {len(hr_permissions_list)} permissions.")


    # Supervisor Group
    supervisor_permissions_list = []
    payroll_models_for_supervisor = {
        LeaveRequest: ['change_leaverequest', 'view_leaverequest'], # Approve/reject (change) and view
        LeavePolicy: ['view_leavepolicy'],
        EmployeeProfile: ['view_employeeprofile'],
        PerformanceReview: ['view_performancereview', 'add_performancereview'],
    }
    for model, codenames in payroll_models_for_supervisor.items():
        try:
            ct = ContentType.objects.get_for_model(model)
            supervisor_permissions_list.extend(Permission.objects.filter(content_type=ct, codename__in=codenames))
        except ContentType.DoesNotExist:
            print(f"Warning: ContentType for {model.__name__} not found. Skipping its supervisor permissions.")
    supervisor_group.permissions.set(supervisor_permissions_list)
    print(f"Configured Supervisor group with {len(supervisor_permissions_list)} permissions.")


    # Employee Group
    employee_permissions_list = []
    payroll_models_for_employee = {
        LeaveRequest: ['add_leaverequest', 'view_leaverequest', 'delete_leaverequest'], # Add own, view own, delete own (if pending)
        LeavePolicy: ['view_leavepolicy'],
        IOU: ['add_iou', 'view_iou', 'delete_iou'], # Add own, view own, delete own (if pending)
        EmployeeProfile: ['view_employeeprofile', 'change_employeeprofile'],
        Payroll: ['view_payroll'],
        PerformanceReview: ['view_performancereview'],
    }
    for model, codenames in payroll_models_for_employee.items():
        try:
            ct = ContentType.objects.get_for_model(model)
            employee_permissions_list.extend(Permission.objects.filter(content_type=ct, codename__in=codenames))
        except ContentType.DoesNotExist:
            print(f"Warning: ContentType for {model.__name__} not found. Skipping its employee permissions.")
    employee_group.permissions.set(employee_permissions_list)
    print(f"Configured Employee group with {len(employee_permissions_list)} permissions.")

    print("Default groups and permissions configuration complete.")

# This allows the script to be imported without running the setup immediately,
# or to be run directly (e.g., via `python manage.py shell < payroll/permissions.py`)
if __name__ == '__main__':
    # This part won't run when Django imports the file during startup.
    # It's more for direct execution or if called from a management command.
    # For automatic setup, use signals (e.g., post_migrate).
    # For this subtask, simply defining the function is sufficient.
    # To actually run it, you'd need to call setup_groups_and_permissions()
    # from a Django management command or a post_migrate signal.
    pass

# Example of how to connect to post_migrate signal (in apps.py or signals.py):
# from django.db.models.signals import post_migrate
# from django.dispatch import receiver
# from .permissions import setup_groups_and_permissions

# @receiver(post_migrate)
# def on_post_migrate(sender, **kwargs):
#     if sender.name == 'payroll': # or your app name
#         setup_groups_and_permissions()
