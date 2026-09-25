from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies=[("leads","0003_lead_normalized_identity")]
    operations=[
        migrations.AlterField(model_name="followup",name="status",field=models.CharField(choices=[("draft","Draft"),("approved","Approved"),("sent","Sent"),("cancelled","Cancelled")],default="draft",max_length=20)),
        migrations.AddField(model_name="followup",name="created_at",field=models.DateTimeField(auto_now_add=True,null=True)),
    ]
