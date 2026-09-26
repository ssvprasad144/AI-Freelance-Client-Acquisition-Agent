from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("leads", "0011_source_aware_outreach")]

    operations = [
        migrations.CreateModel(
            name="Proposal",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("draft","Draft"),("approved","Approved"),("archived","Archived")], db_index=True, default="draft", max_length=20)),
                ("current_version", models.PositiveIntegerField(default=1)),
                ("delivery_medium", models.CharField(blank=True, max_length=40)),
                ("approved_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("lead", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="proposals", to="leads.lead")),
            ],
            options={"ordering":["-created_at"]},
        ),
        migrations.CreateModel(
            name="ProposalVersion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("version_number", models.PositiveIntegerField()),
                ("content", models.TextField()),
                ("source", models.CharField(default="ai", max_length=20)),
                ("instruction", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("proposal", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="versions", to="leads.proposal")),
            ],
            options={"ordering":["-version_number"]},
        ),
        migrations.AddConstraint(
            model_name="proposalversion",
            constraint=models.UniqueConstraint(fields=("proposal","version_number"), name="unique_proposal_version"),
        ),
        migrations.AddField(model_name="outreach", name="proposal", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="outreach", to="leads.proposal")),
        migrations.CreateModel(
            name="FollowUpSequence",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(default="Default follow-up", max_length=120)),
                ("status", models.CharField(choices=[("active","Active"),("paused","Paused"),("completed","Completed"),("cancelled","Cancelled")], db_index=True, default="active", max_length=20)),
                ("max_steps", models.PositiveSmallIntegerField(default=3)),
                ("stop_on_reply", models.BooleanField(default=True)),
                ("stop_on_terminal_status", models.BooleanField(default=True)),
                ("current_step", models.PositiveSmallIntegerField(default=0)),
                ("delays_days", models.JSONField(blank=True, default=list)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("lead", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="followup_sequences", to="leads.lead")),
            ],
        ),
        migrations.AddField(model_name="followup", name="sequence", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="followups", to="leads.followupsequence")),
        migrations.AddField(model_name="followup", name="step_number", field=models.PositiveSmallIntegerField(default=1)),
        migrations.AddField(model_name="reply", name="urgency", field=models.CharField(blank=True, max_length=20)),
        migrations.AddField(model_name="reply", name="confidence", field=models.PositiveSmallIntegerField(default=0)),
        migrations.AddField(model_name="reply", name="extracted_questions", field=models.JSONField(blank=True, default=list)),
        migrations.AddField(model_name="reply", name="recommended_action", field=models.TextField(blank=True)),
        migrations.AddField(model_name="reply", name="suggested_response", field=models.TextField(blank=True)),
        migrations.AddField(model_name="reply", name="next_action", field=models.CharField(blank=True, max_length=50)),
    ]
