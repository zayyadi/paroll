from django.db.models.signals import post_save
from django.dispatch import receiver

from company.models import CompanyMembership
from users.models import CustomUser


@receiver(post_save, sender=CustomUser)
def ensure_user_membership(sender, instance, created, **kwargs):
    if kwargs.get("raw", False):
        return

    target_company = instance.active_company or instance.company
    if target_company is None:
        return

    membership, membership_created = CompanyMembership.objects.get_or_create(
        user=instance,
        company=target_company,
        defaults={"is_default": True, "role": CompanyMembership.ROLE_MEMBER},
    )
    if membership_created:
        CompanyMembership.objects.filter(
            user=instance,
            is_default=True,
        ).exclude(pk=membership.pk).update(is_default=False)

    if instance.company_id is None:
        CustomUser.objects.filter(pk=instance.pk).update(company=target_company)
    if instance.active_company_id is None:
        CustomUser.objects.filter(pk=instance.pk).update(active_company=target_company)
