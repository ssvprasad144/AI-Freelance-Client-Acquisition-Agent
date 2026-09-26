from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies=[("leads","0007_discovery_query_cache")]
    operations=[
        migrations.CreateModel(name="DiscoverySearchStat",fields=[
            ("id",models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name="ID")),
            ("profile_id",models.CharField(db_index=True,max_length=100)),
            ("query",models.CharField(max_length=1000)),
            ("normalized_query",models.CharField(db_index=True,max_length=1000)),
            ("source",models.CharField(db_index=True,default="web_search",max_length=100)),
            ("search_date",models.DateField(db_index=True)),
            ("raw_results",models.PositiveIntegerField(default=0)),
            ("valid_results",models.PositiveIntegerField(default=0)),
            ("unique_results",models.PositiveIntegerField(default=0)),
            ("scored_candidates",models.PositiveIntegerField(default=0)),
            ("crawled_candidates",models.PositiveIntegerField(default=0)),
            ("newly_created_leads",models.PositiveIntegerField(default=0)),
            ("duplicates",models.PositiveIntegerField(default=0)),
            ("locally_filtered",models.PositiveIntegerField(default=0)),
            ("ai_calls",models.PositiveIntegerField(default=0)),
            ("analyzed",models.PositiveIntegerField(default=0)),
            ("qualified",models.PositiveIntegerField(default=0)),
            ("replied",models.PositiveIntegerField(default=0)),
            ("won",models.PositiveIntegerField(default=0)),
            ("created_at",models.DateTimeField(auto_now_add=True)),
            ("updated_at",models.DateTimeField(auto_now=True)),
        ],options={"ordering":["-search_date","-created_at"]}),
        migrations.AddIndex(model_name="discoverysearchstat",index=models.Index(fields=["profile_id","search_date"],name="leads_disc_profile_1a6e8f_idx")),
        migrations.AddIndex(model_name="discoverysearchstat",index=models.Index(fields=["source","search_date"],name="leads_disc_source_6f7db8_idx")),
    ]
