from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies=[("leads","0017_revenue_intelligence")]
    operations=[
        migrations.AddField(model_name="acquisitionopportunity",name="execution_count",field=models.PositiveSmallIntegerField(default=0)),
        migrations.AddField(model_name="acquisitionopportunity",name="last_action",field=models.CharField(blank=True,max_length=60)),
        migrations.AddField(model_name="acquisitionopportunity",name="last_error",field=models.TextField(blank=True)),
        migrations.AddField(model_name="outreachplan",name="attempt_count",field=models.PositiveSmallIntegerField(default=0)),
        migrations.AddField(model_name="outreachplan",name="last_attempt_at",field=models.DateTimeField(blank=True,null=True)),
        migrations.AddField(model_name="revenuerecord",name="source",field=models.CharField(blank=True,db_index=True,max_length=100)),
        migrations.AddField(model_name="revenuerecord",name="profile_id",field=models.CharField(blank=True,db_index=True,max_length=100)),
        migrations.AddField(model_name="revenuerecord",name="strategy_id",field=models.CharField(blank=True,db_index=True,max_length=100)),
        migrations.AddField(model_name="revenuerecord",name="domain",field=models.CharField(blank=True,db_index=True,max_length=255)),
        migrations.AddField(model_name="revenuerecord",name="query_family",field=models.CharField(blank=True,db_index=True,max_length=120)),
        migrations.AddField(model_name="revenuerecord",name="channel",field=models.CharField(blank=True,db_index=True,max_length=40)),
        migrations.AddField(model_name="revenuerecord",name="message_variant",field=models.CharField(blank=True,max_length=20)),
    ]
