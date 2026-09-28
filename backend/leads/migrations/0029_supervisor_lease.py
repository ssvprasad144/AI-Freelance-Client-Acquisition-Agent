from django.db import migrations, models


def seed_lease(apps, schema_editor):
    Lease = apps.get_model("leads", "SupervisorLease")
    Lease.objects.get_or_create(key="acquisition-supervisor")


class Migration(migrations.Migration):
    dependencies = [("leads", "0028_targeted_query_indexes")]
    operations = [
        migrations.CreateModel(
            name="SupervisorLease",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("key", models.CharField(max_length=100, unique=True)),
                ("run_id", models.CharField(blank=True, max_length=64)),
                ("locked_until", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.RunPython(seed_lease, migrations.RunPython.noop),
    ]
