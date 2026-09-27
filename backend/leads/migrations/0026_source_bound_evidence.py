from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("leads", "0025_lead_owner_url_unique"),
    ]

    operations = [
        migrations.AddField(
            model_name="discoveryquerycache",
            name="source_findings",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.CreateModel(
            name="LeadEvidence",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("field_name", models.CharField(max_length=100)),
                ("value", models.TextField()),
                ("evidence_hash", models.CharField(max_length=64)),
                ("source_url", models.URLField(blank=True)),
                ("excerpt", models.TextField(blank=True)),
                ("origin", models.CharField(choices=[("extracted", "Extracted"), ("ai_inferred", "AI inferred"), ("crawler", "Crawler")], default="extracted", max_length=30)),
                ("validation_status", models.CharField(choices=[("validated", "Validated"), ("unvalidated", "Unvalidated")], default="unvalidated", max_length=30)),
                ("source_supported", models.BooleanField(default=False)),
                ("observed_at", models.DateTimeField()),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("lead", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="evidence", to="leads.lead")),
            ],
            options={
                "ordering": ["field_name", "id"],
            },
        ),
        migrations.AddConstraint(
            model_name="leadevidence",
            constraint=models.UniqueConstraint(fields=["lead", "evidence_hash"], name="unique_lead_evidence_hash"),
        ),
    ]
