from django.db import models


class AutoSlugField(models.SlugField):
    def __init__(self, *args, populate_from=None, unique_with=None, **kwargs):
        self.populate_from = populate_from
        self.unique_with = unique_with
        kwargs.pop("always_update", None)
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        path = "autoslug.fields.AutoSlugField"
        if self.populate_from is not None:
            kwargs["populate_from"] = self.populate_from
        if self.unique_with is not None:
            kwargs["unique_with"] = self.unique_with
        return name, path, args, kwargs
