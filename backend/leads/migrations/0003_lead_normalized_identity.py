from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies=[("leads","0002_lead_freshness")]
    operations=[
        migrations.AddField(model_name="lead",name="normalized_title",field=models.CharField(blank=True,db_index=True,max_length=255)),
        migrations.AddField(model_name="lead",name="normalized_url",field=models.CharField(blank=True,db_index=True,max_length=500)),
    ]
