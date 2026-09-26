from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies=[("leads","0005_followup_created_at")]
    operations=[migrations.CreateModel(name="Reply",fields=[
        ("id",models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name="ID")),
        ("channel",models.CharField(default="email",max_length=30)),
        ("message",models.TextField()),
        ("sentiment",models.CharField(blank=True,max_length=30)),
        ("intent",models.CharField(blank=True,max_length=50)),
        ("created_at",models.DateTimeField(auto_now_add=True)),
        ("lead",models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name="replies",to="leads.lead")),
    ])]
