from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies=[("leads","0001_initial")]
    operations=[
        migrations.AddField(model_name="lead",name="posted_at",field=models.DateTimeField(blank=True,null=True)),
        migrations.AddField(model_name="lead",name="expires_at",field=models.DateTimeField(blank=True,null=True)),
        migrations.AddField(model_name="lead",name="last_verified_at",field=models.DateTimeField(blank=True,null=True)),
    ]
