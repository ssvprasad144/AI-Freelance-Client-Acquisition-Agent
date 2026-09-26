import os

from django.contrib.auth import get_user_model
from django.db import migrations


def bootstrap_initial_admin(apps, schema_editor):
    enabled = os.getenv("BOOTSTRAP_ADMIN_ENABLED", "false").strip().lower() == "true"
    if not enabled:
        return

    username = os.getenv("DJANGO_ADMIN_USERNAME", "").strip()
    password = os.getenv("DJANGO_ADMIN_PASSWORD", "")
    email = os.getenv("DJANGO_ADMIN_EMAIL", "").strip()

    if not username or not password:
        raise RuntimeError(
            "BOOTSTRAP_ADMIN_ENABLED=true requires DJANGO_ADMIN_USERNAME "
            "and DJANGO_ADMIN_PASSWORD."
        )

    User = get_user_model()
    user, created = User.objects.get_or_create(
        username=username,
        defaults={
            "email": email,
            "is_staff": True,
            "is_superuser": True,
            "is_active": True,
        },
    )

    if created:
        user.set_password(password)
        user.save(update_fields=["password"])
        return

    if not user.is_superuser or not user.is_staff or not user.is_active:
        raise RuntimeError(
            f"User '{username}' already exists but is not an active "
            "Django superuser/staff account."
        )


class Migration(migrations.Migration):
    dependencies = [
        ("leads", "0018_phase_16_18_completion"),
    ]

    operations = [
        migrations.RunPython(bootstrap_initial_admin, migrations.RunPython.noop),
    ]
