from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("leads", "0020_phase_1_lead_integrity")]

    operations = [
        migrations.AlterField(
            model_name="contact",
            name="normalized_profile_url",
            field=models.CharField(blank=True, db_index=True, max_length=2048),
        ),
    ]
