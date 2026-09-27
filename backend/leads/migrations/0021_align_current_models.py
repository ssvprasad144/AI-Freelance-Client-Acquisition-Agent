from django.db import migrations, models
from django.utils import timezone


def backfill_followup_created_at(apps, schema_editor):
    FollowUp = apps.get_model("leads", "FollowUp")
    FollowUp.objects.filter(created_at__isnull=True).update(created_at=timezone.now())


class Migration(migrations.Migration):
    dependencies = [("leads", "0020_tenant_ownership")]

    operations = [
        migrations.AlterModelOptions(
            name="client",
            options={"ordering": ["-updated_at"]},
        ),
        migrations.AlterModelOptions(
            name="discoverydomainstat",
            options={"ordering": ["-qualified", "-results"]},
        ),
        migrations.RenameIndex(
            model_name="discoverysearchstat",
            old_name="leads_disc_profile_1a6e8f_idx",
            new_name="leads_disco_profile_b1154a_idx",
        ),
        migrations.RenameIndex(
            model_name="discoverysearchstat",
            old_name="leads_disc_source_6f7db8_idx",
            new_name="leads_disco_source_825e27_idx",
        ),
        migrations.RunPython(backfill_followup_created_at, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="followup",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True),
        ),
        migrations.AlterField(
            model_name="followup",
            name="status",
            field=models.CharField(default="draft", max_length=20),
        ),
        migrations.AlterField(
            model_name="followupsequence",
            name="status",
            field=models.CharField(
                choices=[
                    ("active", "Active"),
                    ("paused", "Paused"),
                    ("completed", "Completed"),
                    ("cancelled", "Cancelled"),
                ],
                default="active",
                max_length=20,
            ),
        ),
    ]
