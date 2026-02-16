from django.contrib.auth import get_user_model
from django.test import TestCase
from django.core.cache import cache
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.urls import reverse
from django.test import override_settings


class UsersManagersTests(TestCase):
    def test_create_user(self):
        User = get_user_model()
        user = User.objects.create_user(email="normal@user.com", password="foo")
        self.assertEqual(user.email, "normal@user.com")
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        try:
            # username is None for the AbstractUser option
            # username does not exist for the AbstractBaseUser option
            self.assertIsNone(user.username)
        except AttributeError:
            pass
        with self.assertRaises(TypeError):
            User.objects.create_user()
        with self.assertRaises(TypeError):
            User.objects.create_user(email="")
        with self.assertRaises(ValueError):
            User.objects.create_user(email="", password="foo")

    def test_create_superuser(self):
        User = get_user_model()
        admin_user = User.objects.create_superuser(
            email="super@user.com", password="foo"
        )
        self.assertEqual(admin_user.email, "super@user.com")
        self.assertTrue(admin_user.is_active)
        self.assertTrue(admin_user.is_staff)
        self.assertTrue(admin_user.is_superuser)
        try:
            # username is None for the AbstractUser option
            # username does not exist for the AbstractBaseUser option
            self.assertIsNone(admin_user.username)
        except AttributeError:
            pass
        with self.assertRaises(ValueError):
            User.objects.create_superuser(
                email="super@user.com", password="foo", is_superuser=False
            )


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class AccountActivationTests(TestCase):
    def setUp(self):
        self.User = get_user_model()
        self.user = self.User.objects.create_user(
            email="inactive@example.com",
            first_name="Inactive",
            last_name="User",
            password="StrongPass123!",
            is_active=False,
        )

    def test_activate_account_with_valid_token(self):
        uidb64 = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)
        cache.set(f"registration_otp_{self.user.email}", "123456", timeout=600)

        response = self.client.get(
            reverse("users:activate", kwargs={"uidb64": uidb64, "token": token})
        )
        self.user.refresh_from_db()

        self.assertRedirects(response, reverse("users:login"))
        self.assertTrue(self.user.is_active)
        self.assertIsNone(cache.get(f"registration_otp_{self.user.email}"))

    def test_activate_account_with_invalid_token(self):
        uidb64 = urlsafe_base64_encode(force_bytes(self.user.pk))

        response = self.client.get(
            reverse("users:activate", kwargs={"uidb64": uidb64, "token": "bad-token"})
        )
        self.user.refresh_from_db()

        self.assertEqual(response.status_code, 400)
        self.assertFalse(self.user.is_active)

    def test_verify_registration_otp_missing_email_is_safe(self):
        response = self.client.get(
            reverse("users:verify_registration_otp", kwargs={"email": "missing@x.com"})
        )
        self.assertRedirects(response, reverse("users:register"))

    def test_resend_registration_activation_for_inactive_user(self):
        response = self.client.post(
            reverse(
                "users:resend_registration_activation",
                kwargs={"email": self.user.email},
            )
        )
        self.assertRedirects(
            response,
            reverse(
                "users:verify_registration_otp",
                kwargs={"email": self.user.email},
            ),
        )
        self.assertIsNotNone(cache.get(f"registration_otp_{self.user.email}"))

    def test_resend_registration_activation_is_rate_limited(self):
        self.client.post(
            reverse(
                "users:resend_registration_activation",
                kwargs={"email": self.user.email},
            )
        )
        response = self.client.post(
            reverse(
                "users:resend_registration_activation",
                kwargs={"email": self.user.email},
            ),
            follow=True,
        )
        self.assertContains(response, "Please wait")

    def test_verify_registration_otp_redirects_if_user_is_active(self):
        self.user.is_active = True
        self.user.save(update_fields=["is_active"])
        response = self.client.get(
            reverse(
                "users:verify_registration_otp",
                kwargs={"email": self.user.email},
            )
        )
        self.assertRedirects(response, reverse("users:login"))
