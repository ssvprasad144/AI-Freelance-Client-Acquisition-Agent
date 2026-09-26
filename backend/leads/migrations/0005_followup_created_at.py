from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("leads", "0004_followup_due_status")]
    operations = [
        migrations.AddField(
            model_name="followup",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True, null=True),
        ),
    ]
