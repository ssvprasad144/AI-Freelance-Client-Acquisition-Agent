from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies=[("leads","0008_discovery_search_stat")]
    operations=[migrations.AddField(model_name="discoverysearchstat",name="strategy_id",field=models.CharField(db_index=True,default="general-web",max_length=100))]
