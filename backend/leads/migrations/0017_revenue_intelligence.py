from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies=[("leads","0016_multichannel_outreach")]
    operations=[migrations.CreateModel(name="RevenueRecord",fields=[
        ("id",models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name="ID")),
        ("estimated_value",models.DecimalField(decimal_places=2,default=0,max_digits=14)),
        ("quoted_value",models.DecimalField(decimal_places=2,default=0,max_digits=14)),
        ("won_value",models.DecimalField(decimal_places=2,default=0,max_digits=14)),
        ("expected_value",models.DecimalField(decimal_places=2,default=0,max_digits=14)),
        ("currency",models.CharField(default="USD",max_length=3)),
        ("probability",models.FloatField(default=25)),
        ("search_cost",models.DecimalField(decimal_places=4,default=0,max_digits=14)),
        ("ai_cost",models.DecimalField(decimal_places=4,default=0,max_digits=14)),
        ("crawler_cost",models.DecimalField(decimal_places=4,default=0,max_digits=14)),
        ("outreach_cost",models.DecimalField(decimal_places=4,default=0,max_digits=14)),
        ("created_at",models.DateTimeField(auto_now_add=True)),
        ("updated_at",models.DateTimeField(auto_now=True)),
        ("lead",models.OneToOneField(on_delete=django.db.models.deletion.CASCADE,related_name="revenue",to="leads.lead")),
    ],options={"ordering":["-won_value","-expected_value","-updated_at"]})]
