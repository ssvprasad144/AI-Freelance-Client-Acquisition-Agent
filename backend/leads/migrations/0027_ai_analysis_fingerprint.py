from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("leads", "0026_source_bound_evidence")]
    operations = [
        migrations.AddField(
            model_name="leadanalysis",
            name="input_fingerprint",
            field=models.CharField(default="", max_length=64),
        ),
    ]
