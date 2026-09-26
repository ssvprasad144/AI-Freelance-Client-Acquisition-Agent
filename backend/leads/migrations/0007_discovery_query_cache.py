from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies=[("leads","0006_reply")]
    operations=[
        migrations.CreateModel(
            name="DiscoveryQueryCache",
            fields=[
                ("id",models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name="ID")),
                ("query",models.CharField(max_length=1000)),
                ("normalized_query",models.CharField(db_index=True,max_length=1000)),
                ("profile_id",models.CharField(db_index=True,default="custom",max_length=100)),
                ("searched_at",models.DateTimeField(blank=True,db_index=True,null=True)),
                ("result_count",models.PositiveIntegerField(default=0)),
                ("created_at",models.DateTimeField(auto_now_add=True)),
                ("updated_at",models.DateTimeField(auto_now=True)),
            ],
            options={"ordering":["searched_at","created_at"]},
        ),
        migrations.AddConstraint(
            model_name="discoveryquerycache",
            constraint=models.UniqueConstraint(fields=("profile_id","normalized_query"),name="unique_discovery_query_cache"),
        ),
    ]
