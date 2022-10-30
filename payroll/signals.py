# from django.db.models.signals import post_save
# from django.contrib.auth.models import User
# from django.dispatch import receiver
# from payroll.models import EmployeeProfile


# @receiver(post_save, sender=User)
# def create_employee(sender, instance, created, **kwargs):
#     if created:
#         first_name = instance.first_name
#         last_name = instance.last_name
#         User.objects.filter(pk=instance.pk).update(first_name =first_name, 
#         last_name =last_name)
#         Employee.objects.create(user=instance)

# @receiver(post_save, sender=User)
# def save_employee(sender, instance, **kwargs):
#     first_name = instance.first_name
#     last_name = instance.last_name
#     User.objects.filter(pk=instance.pk).update(first_name =first_name, 
#     last_name =last_name)
#     instance.employee_user.save()

# @receiver(post_save, sender=Employee)
# def create_profile(sender, instance, created, **kwargs):
#     if created:
#         first_name = instance.first_name
#         last_name = instance.last_name
#         email= instance.email
#         Employee.objects.filter(pk=instance.pk).update(
#             first_name=first_name, 
#             last_name=last_name,
#             email=email
#         )
#         EmployeeProfile.objects.create(employee=instance)

# @receiver(post_save, sender=User)
# def save_employee(sender, instance, **kwargs):
#     instance.employee.save()