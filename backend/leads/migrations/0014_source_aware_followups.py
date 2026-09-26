from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies=[("leads","0013_client_intelligence_meetings_learning")]
    operations=[
        migrations.AddField(model_name="followupsequence",name="medium",field=models.CharField(default="email",max_length=40)),
        migrations.AddField(model_name="followupsequence",name="action_type",field=models.CharField(default="send_email",max_length=50)),
        migrations.AddField(model_name="followupsequence",name="destination_url",field=models.URLField(blank=True)),
        migrations.AddField(model_name="followup",name="medium",field=models.CharField(default="email",max_length=40)),
        migrations.AddField(model_name="followup",name="action_type",field=models.CharField(default="send_email",max_length=50)),
        migrations.AddField(model_name="followup",name="destination_url",field=models.URLField(blank=True)),
    ]