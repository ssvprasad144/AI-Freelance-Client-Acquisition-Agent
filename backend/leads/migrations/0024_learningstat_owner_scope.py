from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("leads", "0023_outreach_updated_at"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="learningstat",
            name="unique_learning_dimension_key",
        ),
        migrations.AddConstraint(
            model_name="learningstat",
            constraint=models.UniqueConstraint(
                fields=["owner", "dimension", "key"],
                name="unique_learning_owner_dimension_key",
            ),
        ),
    ]
