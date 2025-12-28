from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from users.models import CustomUser
from payroll.models import (
    LeaveRequest,
    LeavePolicy,
    EmployeeProfile,
    Payroll,
    IOU,
    PerformanceReview,
    Allowance,
    Deduction,
    PayT,
    AuditTrail,
)


def setup_groups_and_permissions():
    print("Setting up default groups and permissions...")

    super_admin_group, _ = Group.objects.get_or_create(name="Super Admin")
    admin_group, _ = Group.objects.get_or_create(name="Admin")
    hr_group, _ = Group.objects.get_or_create(name="HR")
    supervisor_group, _ = Group.objects.get_or_create(name="Supervisor")
    employee_group, _ = Group.objects.get_or_create(name="Employee")

    super_admin_group.permissions.set(Permission.objects.all())
    print(f"Configured Super Admin group with all permissions.")

    admin_permissions_list = []
    try:
        user_ct = ContentType.objects.get_for_model(CustomUser)
        admin_permissions_list.extend(
            Permission.objects.filter(
                content_type=user_ct,
                codename__in=[
                    "view_customuser",
                    "change_customuser",
                    "add_customuser",
                    "delete_customuser",
                ],
            )
        )
    except ContentType.DoesNotExist:
        print(
            "Warning: ContentType for CustomUser not found. Skipping CustomUser admin permissions."
        )

    payroll_models_for_admin = {
        LeaveRequest: [
            "add_leaverequest",
            "change_leaverequest",
            "delete_leaverequest",
            "view_leaverequest",
        ],
        LeavePolicy: [
            "add_leavepolicy",
            "change_leavepolicy",
            "delete_leavepolicy",
            "view_leavepolicy",
        ],
        EmployeeProfile: [
            "add_employeeprofile",
            "change_employeeprofile",
            "delete_employeeprofile",
            "view_employeeprofile",
        ],
        Payroll: ["add_payroll", "change_payroll", "delete_payroll", "view_payroll"],
        PayT: ["add_payt", "change_payt", "delete_payt", "view_payt"],
        IOU: ["add_iou", "change_iou", "delete_iou", "view_iou"],
        Allowance: [
            "add_allowance",
            "change_allowance",
            "delete_allowance",
            "view_allowance",
        ],
        Deduction: [
            "add_deduction",
            "change_deduction",
            "delete_deduction",
            "view_deduction",
        ],
        PerformanceReview: [
            "add_performancereview",
            "change_performancereview",
            "delete_performancereview",
            "view_performancereview",
        ],
        AuditTrail: ["view_audittrail"],
    }
    for model, codenames in payroll_models_for_admin.items():
        try:
            ct = ContentType.objects.get_for_model(model)
            admin_permissions_list.extend(
                Permission.objects.filter(content_type=ct, codename__in=codenames)
            )
        except ContentType.DoesNotExist:
            print(
                f"Warning: ContentType for {model.__name__} not found. Skipping its admin permissions."
            )
    admin_group.permissions.set(admin_permissions_list)
    print(f"Configured Admin group with {len(admin_permissions_list)} permissions.")

    hr_permissions_list = []
    try:
        user_ct = ContentType.objects.get_for_model(CustomUser)

        hr_permissions_list.extend(
            Permission.objects.filter(
                content_type=user_ct,
                codename__in=["view_customuser", "change_customuser"],
            )
        )
    except ContentType.DoesNotExist:
        print(
            "Warning: ContentType for CustomUser not found. Skipping CustomUser HR permissions."
        )

    payroll_models_for_hr = {
        LeaveRequest: [
            "add_leaverequest",
            "change_leaverequest",
            "view_leaverequest",
            "delete_leaverequest",
        ],
        LeavePolicy: [
            "add_leavepolicy",
            "change_leavepolicy",
            "delete_leavepolicy",
            "view_leavepolicy",
        ],
        EmployeeProfile: [
            "add_employeeprofile",
            "change_employeeprofile",
            "view_employeeprofile",
            "delete_employeeprofile",
        ],
        PerformanceReview: [
            "add_performancereview",
            "change_performancereview",
            "view_performancereview",
            "delete_performancereview",
        ],
        IOU: ["add_iou", "change_iou", "delete_iou", "view_iou"],
        Payroll: ["view_payroll", "change_payroll"],
        PayT: ["view_payt", "change_payt"],
        Allowance: [
            "add_allowance",
            "change_allowance",
            "delete_allowance",
            "view_allowance",
        ],
        Deduction: [
            "add_deduction",
            "change_deduction",
            "delete_deduction",
            "view_deduction",
        ],
    }
    for model, codenames in payroll_models_for_hr.items():
        try:
            ct = ContentType.objects.get_for_model(model)
            hr_permissions_list.extend(
                Permission.objects.filter(content_type=ct, codename__in=codenames)
            )
        except ContentType.DoesNotExist:
            print(
                f"Warning: ContentType for {model.__name__} not found. Skipping its HR permissions."
            )
    hr_group.permissions.set(hr_permissions_list)
    print(f"Configured HR group with {len(hr_permissions_list)} permissions.")

    supervisor_permissions_list = []
    payroll_models_for_supervisor = {
        LeaveRequest: ["change_leaverequest", "view_leaverequest"],
        LeavePolicy: ["view_leavepolicy"],
        EmployeeProfile: ["view_employeeprofile"],
        PerformanceReview: ["view_performancereview", "add_performancereview"],
    }
    for model, codenames in payroll_models_for_supervisor.items():
        try:
            ct = ContentType.objects.get_for_model(model)
            supervisor_permissions_list.extend(
                Permission.objects.filter(content_type=ct, codename__in=codenames)
            )
        except ContentType.DoesNotExist:
            print(
                f"Warning: ContentType for {model.__name__} not found. Skipping its supervisor permissions."
            )
    supervisor_group.permissions.set(supervisor_permissions_list)
    print(
        f"Configured Supervisor group with {len(supervisor_permissions_list)} permissions."
    )

    employee_permissions_list = []
    payroll_models_for_employee = {
        LeaveRequest: ["add_leaverequest", "view_leaverequest", "delete_leaverequest"],
        LeavePolicy: ["view_leavepolicy"],
        IOU: ["add_iou", "view_iou", "delete_iou"],
        EmployeeProfile: ["view_employeeprofile", "change_employeeprofile"],
        Payroll: ["view_payroll"],
        PerformanceReview: ["view_performancereview"],
    }
    for model, codenames in payroll_models_for_employee.items():
        try:
            ct = ContentType.objects.get_for_model(model)
            employee_permissions_list.extend(
                Permission.objects.filter(content_type=ct, codename__in=codenames)
            )
        except ContentType.DoesNotExist:
            print(
                f"Warning: ContentType for {model.__name__} not found. Skipping its employee permissions."
            )
    employee_group.permissions.set(employee_permissions_list)
    print(
        f"Configured Employee group with {len(employee_permissions_list)} permissions."
    )

    print("Default groups and permissions configuration complete.")


if __name__ == "__main__":

    pass
