import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import models


ENCRYPTED_PREFIX = "enc:v1:"


def _fernet() -> Fernet:
    digest = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


class EncryptedCharField(models.CharField):
    description = "CharField encrypted at rest with the Django SECRET_KEY"

    def get_internal_type(self):
        return "CharField"

    def from_db_value(self, value, expression, connection):
        return self._decrypt(value)

    def to_python(self, value):
        value = super().to_python(value)
        return self._decrypt(value)

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value in (None, "") or str(value).startswith(ENCRYPTED_PREFIX):
            return value
        token = _fernet().encrypt(str(value).encode("utf-8")).decode("ascii")
        return f"{ENCRYPTED_PREFIX}{token}"

    def _decrypt(self, value):
        if value in (None, ""):
            return value
        value = str(value)
        if not value.startswith(ENCRYPTED_PREFIX):
            return value
        token = value[len(ENCRYPTED_PREFIX) :]
        try:
            return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
        except (InvalidToken, ValueError):
            return value
