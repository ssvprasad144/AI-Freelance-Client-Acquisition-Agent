from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies=[("leads","0015_autonomous_acquisition")]
    operations=[migrations.CreateModel(name="OutreachPlan",fields=[
        ("id",models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name="ID")),
        ("channel",models.CharField(db_index=True,max_length=40)),
        ("variant",models.CharField(default="A",max_length=20)),
        ("message",models.TextField()),
        ("destination_url",models.URLField(blank=True)),
        ("automatic",models.BooleanField(default=False)),
        ("status",models.CharField(default="draft",max_length=20,db_index=True)),
        ("approved_at",models.DateTimeField(blank=True,null=True)),
        ("sent_at",models.DateTimeField(blank=True,null=True)),
        ("last_reason",models.TextField(blank=True)),
        ("created_at",models.DateTimeField(auto_now_add=True)),
        ("updated_at",models.DateTimeField(auto_now=True)),
        ("lead",models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name="outreach_plans",to="leads.lead")),
    ],options={"ordering":["-updated_at"],"constraints":[models.UniqueConstraint(fields=["lead","channel","variant"],name="unique_outreach_plan_variant")]} )]
