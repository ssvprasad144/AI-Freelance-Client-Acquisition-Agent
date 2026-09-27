from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("leads", "0021_normalized_profile_url_length")]

    operations = [
        migrations.AddField(
            model_name="discoveryquerycache",
            name="source_findings",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
