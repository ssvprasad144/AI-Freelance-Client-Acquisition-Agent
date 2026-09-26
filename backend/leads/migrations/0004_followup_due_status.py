from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies=[("leads","0003_lead_normalized_identity")]
    operations=[
        migrations.AlterField(
            model_name="followup",
            name="status",
            field=models.CharField(
                choices=[
                    ("draft","Draft"),
                    ("approved","Approved"),
                    ("due","Due"),
                    ("sent","Sent"),
                    ("cancelled","Cancelled"),
                ],
                default="draft",
                max_length=20,
            ),
        ),
    ]
