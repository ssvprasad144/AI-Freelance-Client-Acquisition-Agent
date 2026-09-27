from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def backfill_learning_owners(apps, schema_editor):
    User = apps.get_model("auth", "User")
    LearningStat = apps.get_model("leads", "LearningStat")
    owner = User.objects.filter(is_staff=True).order_by("id").first() or User.objects.order_by("id").first()
    if owner:
        LearningStat.objects.filter(owner__isnull=True).update(owner_id=owner.id)


class Migration(migrations.Migration):
    dependencies = [
        ("leads", "0020_tenant_ownership"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="learningstat",
            name="owner",
            field=models.ForeignKey(
                blank=True,
                db_index=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="acquisition_learning_stats",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunPython(backfill_learning_owners, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="learningstat",
            name="owner",
            field=models.ForeignKey(
                db_index=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="acquisition_learning_stats",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
