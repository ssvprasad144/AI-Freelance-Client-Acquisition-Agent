from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [("leads", "0022_followup_updated_at")]
    operations = [
        migrations.AddField(
            model_name="outreach",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, null=True),
        ),
    ]
