from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("leads", "0021_align_current_models")]

    operations = [
        migrations.AddField(
            model_name="followup",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, null=True),
        ),
    ]
