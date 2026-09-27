from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("leads", "0024_learningstat_owner_scope"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="lead",
            constraint=models.UniqueConstraint(
                fields=["owner", "normalized_url"],
                condition=~models.Q(normalized_url=""),
                name="unique_lead_owner_normalized_url",
            ),
        ),
    ]
