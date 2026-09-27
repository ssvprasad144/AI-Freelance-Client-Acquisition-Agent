from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("leads", "0027_ai_analysis_fingerprint")]

    operations = [
        migrations.AddIndex(model_name="lead", index=models.Index(fields=["owner", "status"], name="lead_owner_status_idx")),
        migrations.AddIndex(model_name="lead", index=models.Index(fields=["owner", "updated_at"], name="lead_owner_updated_idx")),
        migrations.AddIndex(model_name="lead", index=models.Index(fields=["owner", "discovered_at"], name="lead_owner_discovered_idx")),
        migrations.AddIndex(model_name="proposal", index=models.Index(fields=["lead", "status"], name="proposal_lead_status_idx")),
        migrations.AddIndex(model_name="proposal", index=models.Index(fields=["lead", "updated_at"], name="proposal_lead_updated_idx")),
        migrations.AddIndex(model_name="outreach", index=models.Index(fields=["lead", "status"], name="outreach_lead_status_idx")),
        migrations.AddIndex(model_name="outreach", index=models.Index(fields=["lead", "updated_at"], name="outreach_lead_updated_idx")),
        migrations.AddIndex(model_name="followup", index=models.Index(fields=["lead", "status", "scheduled_at"], name="followup_due_idx")),
        migrations.AddIndex(model_name="followup", index=models.Index(fields=["lead", "updated_at"], name="followup_lead_updated_idx")),
        migrations.AddIndex(model_name="activitylog", index=models.Index(fields=["lead", "created_at"], name="activity_lead_created_idx")),
        migrations.AddIndex(model_name="activitylog", index=models.Index(fields=["event_type", "created_at"], name="activity_event_created_idx")),
    ]
