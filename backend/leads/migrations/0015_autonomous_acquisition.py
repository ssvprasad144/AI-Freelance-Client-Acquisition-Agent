from django.db import migrations, models
from django.conf import settings
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies=[("leads","0014_source_aware_followups")]
    operations=[migrations.CreateModel(name="AcquisitionOpportunity",fields=[
        ("id",models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name="ID")),
        ("score",models.FloatField(default=0,db_index=True)),
        ("stage",models.CharField(default="new",max_length=30,db_index=True)),
        ("recommended_action",models.CharField(default="review",max_length=60,db_index=True)),
        ("action_category",models.CharField(default="",max_length=60)),
        ("reason",models.TextField(blank=True)),
        ("status",models.CharField(default="ready",max_length=30,db_index=True)),
        ("executed_at",models.DateTimeField(blank=True,null=True)),
        ("created_at",models.DateTimeField(auto_now_add=True)),
        ("updated_at",models.DateTimeField(auto_now=True)),
        ("lead",models.OneToOneField(on_delete=django.db.models.deletion.CASCADE,related_name="opportunity",to="leads.lead")),
    ],options={"ordering":["-score","-updated_at"]})]
