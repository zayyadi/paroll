from django.contrib.auth.base_user import BaseUserManager
from django.conf import settings
from django.utils.translation import gettext_lazy as _


class CustomUserManager(BaseUserManager):
    """
    Custom user model manager where email is the unique identifiers
    for authentication instead of usernames.
    """

    def create_user(self, email, password, **extra_fields):
        """
        Create and save a user with the given email and password.
        """
        if not email:
            raise ValueError(_("The Email must be set"))
        if not extra_fields.get("company"):
            from company.models import Company

            company, created = Company.objects.get_or_create(name="Default Company")
            extra_fields["company"] = company
        if not extra_fields.get("active_company"):
            extra_fields["active_company"] = extra_fields["company"]
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save()
        if settings.MULTI_COMPANY_MEMBERSHIP_ENABLED:
            from company.models import CompanyMembership

            CompanyMembership.objects.get_or_create(
                user=user,
                company=user.active_company or user.company,
                defaults={"is_default": True},
            )
        return user

    def create_superuser(self, email, password, **extra_fields):
        """
        Create and save a SuperUser with the given email and password.
        """
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError(_("Superuser must have is_staff=True."))
        if extra_fields.get("is_superuser") is not True:
            raise ValueError(_("Superuser must have is_superuser=True."))
        return self.create_user(email, password, **extra_fields)
