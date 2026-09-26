from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies=[("leads","0009_discovery_search_stat_strategy")]
    operations=[
        migrations.AddField(model_name="discoveryquerycache",name="query_family",field=models.CharField(db_index=True,default="general",max_length=120)),
        migrations.AddField(model_name="discoveryquerycache",name="query_signature",field=models.CharField(db_index=True,default="",max_length=64)),
        migrations.AddField(model_name="discoveryquerycache",name="result_payload",field=models.JSONField(blank=True,default=list)),
        migrations.AddField(model_name="discoveryquerycache",name="source_domains",field=models.JSONField(blank=True,default=list)),
        migrations.AddField(model_name="discoverysearchstat",name="query_family",field=models.CharField(db_index=True,default="general",max_length=120)),
        migrations.AddField(model_name="discoverysearchstat",name="query_variant",field=models.CharField(db_index=True,default="base",max_length=120)),
        migrations.AddField(model_name="discoverysearchstat",name="source_domains",field=models.JSONField(blank=True,default=list)),
        migrations.AddField(model_name="discoverysearchstat",name="context_size",field=models.CharField(default="low",max_length=20)),
        migrations.CreateModel(name="DiscoveryDomainStat",fields=[
            ("id",models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name="ID")),
            ("domain",models.CharField(max_length=255,unique=True)),("searches",models.PositiveIntegerField(default=0)),("results",models.PositiveIntegerField(default=0)),("qualified",models.PositiveIntegerField(default=0)),("replied",models.PositiveIntegerField(default=0)),("won",models.PositiveIntegerField(default=0)),("last_seen_at",models.DateTimeField(blank=True,null=True)),("blocked_until",models.DateTimeField(blank=True,null=True)),("created_at",models.DateTimeField(auto_now_add=True)),("updated_at",models.DateTimeField(auto_now=True))])
    ]
