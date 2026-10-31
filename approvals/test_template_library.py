from copy import deepcopy
from unittest.mock import patch

from django.conf import settings
from django.template.backends.django import DjangoTemplates
from django.template.loader import get_template
from django.test import SimpleTestCase


class ApprovalTemplateLibraryTests(SimpleTestCase):
    def test_library_loads_when_app_library_discovery_is_stale(self):
        config = deepcopy(settings.TEMPLATES[0])
        config.pop("BACKEND")
        config["NAME"] = "approval-library-regression"
        with patch(
            "django.template.backends.django.get_installed_libraries", return_value={}
        ):
            backend = DjangoTemplates(config)
            template = backend.from_string("{% load approval_workflow %}Registered")
        self.assertEqual(template.render({}), "Registered")

    def test_approval_inbox_and_shared_layout_compile(self):
        for name in ("approvals/inbox.html", "base_new.html"):
            with self.subTest(template=name):
                get_template(name)
