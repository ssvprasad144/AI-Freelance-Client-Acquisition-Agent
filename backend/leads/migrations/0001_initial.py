from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(
            name="Lead",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=255)),
                ("company", models.CharField(blank=True, max_length=255)),
                ("description", models.TextField()),
                ("source", models.CharField(default="mock", max_length=100)),
                ("source_url", models.URLField(blank=True)),
                ("lead_type", models.CharField(choices=[("freelance","Freelance"),("direct","Direct"),("startup","Startup"),("other","Other")], default="freelance", max_length=30)),
                ("budget_text", models.CharField(blank=True, max_length=255)),
                ("technologies", models.JSONField(blank=True, default=list)),
                ("contact_info", models.JSONField(blank=True, default=dict)),
                ("status", models.CharField(choices=[("new","New"),("qualified","Qualified"),("proposal","Proposal"),("contacted","Contacted"),("replied","Replied"),("won","Won"),("lost","Lost"),("archived","Archived")], default="new", max_length=30)),
                ("discovered_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering":["-created_at"]},
        ),
        migrations.CreateModel(
            name="LeadAnalysis",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("relevant", models.BooleanField(default=False)),
                ("match_score", models.PositiveSmallIntegerField(default=0)),
                ("service_match", models.CharField(blank=True, max_length=100)),
                ("requirements", models.JSONField(blank=True, default=list)),
                ("pain_points", models.JSONField(blank=True, default=list)),
                ("recommended_approach", models.TextField(blank=True)),
                ("matching_projects", models.JSONField(blank=True, default=list)),
                ("confidence", models.PositiveSmallIntegerField(default=0)),
                ("model", models.CharField(default="mock", max_length=100)),
                ("input_tokens", models.PositiveIntegerField(default=0)),
                ("output_tokens", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now=True)),
                ("lead", models.OneToOneField(on_delete=models.deletion.CASCADE, related_name="analysis", to="leads.lead")),
            ],
        ),
        migrations.CreateModel(
            name="Outreach",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("channel", models.CharField(default="email", max_length=30)),
                ("message", models.TextField()),
                ("status", models.CharField(default="draft", max_length=20)),
                ("approved_at", models.DateTimeField(blank=True, null=True)),
                ("sent_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("lead", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="outreach", to="leads.lead")),
            ],
        ),
        migrations.CreateModel(
            name="FollowUp",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("scheduled_at", models.DateTimeField()),
                ("message", models.TextField()),
                ("status", models.CharField(choices=[("draft","Draft"),("approved","Approved"),("sent","Sent"),("cancelled","Cancelled")], default="draft", max_length=20)),
                ("approved_at", models.DateTimeField(blank=True, null=True)),
                ("sent_at", models.DateTimeField(blank=True, null=True)),
                ("lead", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="followups", to="leads.lead")),
            ],
        ),
        migrations.CreateModel(
            name="ActivityLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_type", models.CharField(max_length=100)),
                ("message", models.TextField()),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("lead", models.ForeignKey(blank=True, null=True, on_delete=models.deletion.CASCADE, related_name="activity", to="leads.lead")),
            ],
            options={"ordering":["-created_at"]},
        ),
    ]
