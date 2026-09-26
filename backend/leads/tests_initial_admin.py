from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command, CommandError
from django.test import TestCase


class InitialAdminBootstrapTests(TestCase):
    def test_bootstrap_is_disabled_by_default(self):
        with patch.dict("os.environ", {}, clear=False):
            call_command("create_initial_admin")
        self.assertFalse(get_user_model().objects.filter(username="bootstrap-admin").exists())

    def test_bootstrap_creates_superuser(self):
        env = {
            "BOOTSTRAP_ADMIN_ENABLED": "true",
            "DJANGO_ADMIN_USERNAME": "bootstrap-admin",
            "DJANGO_ADMIN_PASSWORD": "safe-test-password",
            "DJANGO_ADMIN_EMAIL": "admin@example.com",
        }
        with patch.dict("os.environ", env, clear=False):
            call_command("create_initial_admin")

        user = get_user_model().objects.get(username="bootstrap-admin")
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_active)
        self.assertTrue(user.check_password("safe-test-password"))

    def test_bootstrap_never_resets_existing_password(self):
        User = get_user_model()
        user = User.objects.create_superuser(
            username="bootstrap-admin",
            email="old@example.com",
            password="original-password",
        )
        env = {
            "BOOTSTRAP_ADMIN_ENABLED": "true",
            "DJANGO_ADMIN_USERNAME": "bootstrap-admin",
            "DJANGO_ADMIN_PASSWORD": "replacement-password",
            "DJANGO_ADMIN_EMAIL": "new@example.com",
        }
        with patch.dict("os.environ", env, clear=False):
            call_command("create_initial_admin")

        user.refresh_from_db()
        self.assertTrue(user.check_password("original-password"))
        self.assertFalse(user.check_password("replacement-password"))
        self.assertEqual(user.email, "old@example.com")

    def test_enabled_bootstrap_requires_credentials(self):
        env = {"BOOTSTRAP_ADMIN_ENABLED": "true"}
        with patch.dict("os.environ", env, clear=False):
            with self.assertRaises(CommandError):
                call_command("create_initial_admin")
