from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("leads", "0010_discovery_cost_intelligence")]

    operations = [
        migrations.AddField(model_name="outreach", name="medium", field=models.CharField(default="email", max_length=40, db_index=True)),
        migrations.AddField(model_name="outreach", name="action_type", field=models.CharField(default="send_email", max_length=50)),
        migrations.AddField(model_name="outreach", name="destination_url", field=models.URLField(blank=True)),
        migrations.AddField(model_name="outreach", name="opened_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="outreach", name="submitted_at", field=models.DateTimeField(blank=True, null=True)),
    ]
