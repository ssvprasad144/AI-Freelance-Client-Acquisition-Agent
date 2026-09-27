from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def backfill_owners(apps, schema_editor):
    User = apps.get_model("auth", "User")
    Lead = apps.get_model("leads", "Lead")
    Client = apps.get_model("leads", "Client")
    owner = User.objects.filter(is_staff=True).order_by("id").first() or User.objects.order_by("id").first()
    if not owner:
        return
    Lead.objects.filter(owner__isnull=True).update(owner_id=owner.id)
    Client.objects.filter(owner__isnull=True).update(owner_id=owner.id)


class Migration(migrations.Migration):
    dependencies = [("leads", "0019_bootstrap_initial_admin"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.AddField(
            model_name="lead",
            name="owner",
            field=models.ForeignKey(blank=True, db_index=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="acquisition_leads", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name="client",
            name="owner",
            field=models.ForeignKey(blank=True, db_index=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="acquisition_clients", to=settings.AUTH_USER_MODEL),
        ),
        migrations.RunPython(backfill_owners, migrations.RunPython.noop),
        migrations.AlterField(model_name="client", name="normalized_company", field=models.CharField(db_index=True, max_length=255)),
        migrations.AddConstraint(model_name="client", constraint=models.UniqueConstraint(fields=["owner", "normalized_company"], name="unique_client_owner_company")),
    ]
