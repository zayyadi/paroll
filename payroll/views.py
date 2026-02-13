# Helper functions
def check_super(user):
    return user.is_superuser


def is_hr_user(user):
    return user.is_authenticated and (
        user.is_staff or user.is_superuser or user.groups.filter(name="HR").exists()
    )
