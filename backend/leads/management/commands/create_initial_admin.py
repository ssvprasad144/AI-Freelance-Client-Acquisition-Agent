import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Create the initial Django superuser from Render environment variables when explicitly enabled."

    def handle(self, *args, **options):
        enabled = os.getenv("BOOTSTRAP_ADMIN_ENABLED", "false").strip().lower() == "true"
        if not enabled:
            self.stdout.write("Initial admin bootstrap disabled; nothing to do.")
            return

        username = os.getenv("DJANGO_ADMIN_USERNAME", "").strip()
        password = os.getenv("DJANGO_ADMIN_PASSWORD", "")
        email = os.getenv("DJANGO_ADMIN_EMAIL", "").strip()

        if not username or not password:
            raise CommandError(
                "BOOTSTRAP_ADMIN_ENABLED=true requires DJANGO_ADMIN_USERNAME and DJANGO_ADMIN_PASSWORD."
            )

        User = get_user_model()
        user, created = User.objects.get_or_create(
            username=username,
            defaults={"email": email, "is_staff": True, "is_superuser": True, "is_active": True},
        )

        if created:
            user.set_password(password)
            user.save(update_fields=["password"])
            self.stdout.write(self.style.SUCCESS("Initial Django admin user created."))
            return

        if not user.is_superuser or not user.is_staff or not user.is_active:
            raise CommandError(
                f"User '{username}' already exists but is not an active Django superuser/staff account."
            )

        self.stdout.write("Initial Django admin user already exists; no changes made.")
