from urllib.parse import urlsplit

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class AccountAccessTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="customer",
            email="customer@example.com",
            password="a-strong-test-password",
        )

    def test_registration_is_available_and_requires_email(self):
        response = self.client.get(reverse("register"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="email" required')

        response = self.client.post(
            reverse("register"),
            {
                "username": "new-customer",
                "password1": "a-strong-test-password",
                "password2": "a-strong-test-password",
            },
        )

        self.assertRedirects(response, reverse("register"))
        self.assertFalse(
            get_user_model().objects.filter(username="new-customer").exists()
        )

        response = self.client.post(
            reverse("register"),
            {
                "username": "new-customer",
                "email": "new-customer@example.com",
                "password1": "a-strong-test-password",
                "password2": "a-strong-test-password",
            },
        )

        self.assertRedirects(response, reverse("product_list"))
        new_user = get_user_model().objects.get(username="new-customer")
        self.assertEqual(new_user.email, "new-customer@example.com")
        self.assertTrue(new_user.check_password("a-strong-test-password"))

    def test_password_reset_email_changes_password(self):
        response = self.client.post(
            reverse("password_reset"),
            {"email": self.user.email},
        )

        self.assertRedirects(response, reverse("password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        reset_url = next(
            line
            for line in mail.outbox[0].body.splitlines()
            if "/password-reset/confirm/" in line
        )
        reset_path = urlsplit(reset_url).path

        response = self.client.get(reset_path)
        self.assertEqual(response.status_code, 302)
        response = self.client.get(response.url)
        self.assertContains(response, "Choose a new password")

        response = self.client.post(
            response.request["PATH_INFO"],
            {
                "new_password1": "a-new-strong-password-925!",
                "new_password2": "a-new-strong-password-925!",
            },
        )

        self.assertRedirects(response, reverse("password_reset_complete"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("a-new-strong-password-925!"))

    def test_unknown_email_gets_generic_confirmation_without_email(self):
        response = self.client.post(
            reverse("password_reset"),
            {"email": "unknown@example.com"},
        )

        self.assertRedirects(response, reverse("password_reset_done"))
        self.assertContains(self.client.get(response.url), "If an account exists")
        self.assertEqual(len(mail.outbox), 0)

    def test_storefront_and_admin_login_link_to_recovery_and_registration(self):
        login_page = self.client.get(reverse("login"))
        admin_login_page = self.client.get(reverse("admin:login"))

        self.assertContains(login_page, reverse("register"))
        self.assertContains(login_page, reverse("password_reset"))
        self.assertContains(admin_login_page, reverse("password_reset"))
