import os
from uuid import uuid4
from django.db import models
from django.db.models import JSONField
from django.utils.timezone import now

from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey


from core import settings


class SoftDeleteManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)


class SoftDeleteModel(models.Model):
    """
    Abstract model to add soft delete functionality.
    """

    deleted_at = models.DateTimeField(null=True, blank=True, editable=False)

    objects = SoftDeleteManager()
    all_objects = models.Manager()

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False):
        self.deleted_at = now()
        self.save()

    def restore(self):
        self.deleted_at = None
        self.save()

    @property
    def is_deleted(self):
        return self.deleted_at is not None


class AuditTrail(models.Model):
    """
    Model to track changes to other models.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    action = models.CharField(max_length=50)
    timestamp = models.DateTimeField(auto_now_add=True)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")
    changes = JSONField(
        default=dict,
        blank=True,
        help_text="Stores a dictionary of changes (old_value, new_value)",
    )

    def __str__(self):
        return f"{self.user} performed {self.action} on {self.content_object}"


def path_and_rename(instance, filename):
    upload_to = "employee_photo"
    ext = filename.split(".")[-1]
    # get filename
    filename = "{}.{}".format(uuid4().hex, ext)
    # return the whole path to the file
    return os.path.join(upload_to, filename)
