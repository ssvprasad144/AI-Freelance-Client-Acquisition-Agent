from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("leads", "0029_supervisor_lease")]

    operations = [
        migrations.AlterField(
            model_name="followup",
            name="status",
            field=models.CharField(
                choices=[
                    ("draft", "Draft"),
                    ("approved", "Approved"),
                    ("due", "Due"),
                    ("sending", "Sending"),
                    ("send_uncertain", "Send uncertain"),
                    ("sent", "Sent"),
                    ("cancelled", "Cancelled"),
                ],
                default="draft",
                max_length=20,
            ),
        ),
    ]
