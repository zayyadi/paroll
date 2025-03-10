from django.contrib.auth.models import Group, Permission

# Create groups
super_admin_group, _ = Group.objects.get_or_create(name='Super Admin')
admin_group, _ = Group.objects.get_or_create(name='Admin')
hr_group, _ = Group.objects.get_or_create(name='HR')
supervisor_group, _ = Group.objects.get_or_create(name='Supervisor')
employee_group, _ = Group.objects.get_or_create(name='Employee')

# Assign permissions to groups
# Super Admin
super_admin_group.permissions.set(Permission.objects.all())

# Admin
admin_permissions = Permission.objects.filter(codename__in=[
    'view_user', 'change_user',
    'add_leaverequest', 'change_leaverequest', 'delete_leaverequest', 'view_leaverequest',
    'add_leavepolicy', 'change_leavepolicy', 'delete_leavepolicy', 'view_leavepolicy',
])
admin_group.permissions.set(admin_permissions)

# HR
hr_permissions = Permission.objects.filter(codename__in=[
    'view_user',
    'add_leaverequest', 'change_leaverequest', 'view_leaverequest',
    'view_leavepolicy',
])
hr_group.permissions.set(hr_permissions)

# Supervisor
supervisor_permissions = Permission.objects.filter(codename__in=[
    'change_leaverequest', 'view_leaverequest',
    'view_leavepolicy',
])
supervisor_group.permissions.set(supervisor_permissions)

# Employee
employee_permissions = Permission.objects.filter(codename__in=[
    'add_leaverequest', 'view_leaverequest',
    'view_leavepolicy',
])
employee_group.permissions.set(employee_permissions)