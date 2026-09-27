import re

from django.db import migrations, models
from django.db.models import Q
from django.utils import timezone


def backfill_identities(apps, schema_editor):
    Lead = apps.get_model("leads", "Lead")
    Contact = apps.get_model("leads", "Contact")
    alias = schema_editor.connection.alias

    seen_urls = set()
    for lead in Lead.objects.using(alias).order_by("pk").iterator():
        raw = (lead.source_url or "").strip()
        canonical = ""
        try:
            from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
            parts = urlsplit(raw)
            port = parts.port
            host = (parts.hostname or "").rstrip(".").lower().encode("idna").decode("ascii")
            if (parts.scheme.lower() in {"http", "https"} and host and not parts.username and not parts.password
                    and not any(ord(ch) < 32 or ch.isspace() for ch in raw)):
                netloc = host
                if port and not ((parts.scheme.lower() == "http" and port == 80) or (parts.scheme.lower() == "https" and port == 443)):
                    netloc = f"{host}:{port}"
                query = urlencode([(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)
                                   if key.lower() not in {"fbclid", "gclid", "mc_cid", "mc_eid"}
                                   and not key.lower().startswith("utm_")])
                canonical = urlunsplit((parts.scheme.lower(), netloc, (parts.path or "/").rstrip("/") or "/", query, ""))
                if len(canonical) > 2048:
                    canonical = ""
        except (ValueError, UnicodeError):
            canonical = ""
        if canonical and (canonical in seen_urls or len(canonical) > 2048):
            canonical = ""
        if canonical:
            seen_urls.add(canonical)
        title = " ".join(re.sub(r"[^a-z0-9 ]", " ", (lead.title or "").lower()).split())[:255]
        Lead.objects.using(alias).filter(pk=lead.pk).update(normalized_url=canonical, normalized_title=title)

    seen_emails = set()
    seen_profiles = set()
    for contact in Contact.objects.using(alias).order_by("pk").iterator():
        email = (contact.email or "").strip().casefold()
        profile = (contact.profile_url or "").strip().rstrip("/").casefold()
        email_key = (contact.client_id, email)
        profile_key = (contact.client_id, profile)
        if not email or email_key in seen_emails:
            email = ""
        else:
            seen_emails.add(email_key)
        if not profile or profile_key in seen_profiles:
            profile = ""
        else:
            seen_profiles.add(profile_key)
        Contact.objects.using(alias).filter(pk=contact.pk).update(normalized_email=email, normalized_profile_url=profile)

    # Previous code set last_verified_at on first discovery. Historical rows have no
    # source fetch record, so retaining those values would claim evidence we cannot prove.
    Lead.objects.using(alias).update(last_verified_at=None)


class Migration(migrations.Migration):
    dependencies = [("leads", "0019_bootstrap_initial_admin")]

    operations = [
        migrations.AddField(model_name="lead", name="location", field=models.CharField(blank=True, max_length=255)),
        migrations.AddField(model_name="lead", name="company_website", field=models.URLField(blank=True, max_length=2048)),
        migrations.AddField(model_name="lead", name="company_description", field=models.TextField(blank=True)),
        migrations.AddField(model_name="lead", name="hiring_signal", field=models.TextField(blank=True)),
        migrations.AddField(model_name="lead", name="last_checked_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AlterField(model_name="lead", name="source_url", field=models.URLField(blank=True, max_length=2048)),
        migrations.AlterField(model_name="lead", name="action_url", field=models.URLField(blank=True, max_length=2048)),
        migrations.AlterField(model_name="lead", name="normalized_url", field=models.CharField(blank=True, db_index=True, max_length=2048)),
        migrations.AlterField(model_name="contact", name="profile_url", field=models.URLField(blank=True, max_length=2048)),
        migrations.AddField(model_name="contact", name="normalized_email", field=models.CharField(blank=True, db_index=True, max_length=254)),
        migrations.AddField(model_name="contact", name="normalized_profile_url", field=models.CharField(blank=True, db_index=True, max_length=500)),
        migrations.AddField(model_name="discoveryquerycache", name="search_findings", field=models.TextField(blank=True)),
        migrations.CreateModel(
            name="LeadEvidence",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("field_name", models.CharField(db_index=True, max_length=80)),
                ("value", models.TextField()),
                ("evidence_hash", models.CharField(db_index=True, max_length=64)),
                ("source_url", models.URLField(blank=True, max_length=2048)),
                ("excerpt", models.TextField(blank=True)),
                ("origin", models.CharField(choices=[("extracted", "Extracted"), ("ai_inferred", "AI inferred"), ("crawler", "Retrieved page")], default="extracted", max_length=20)),
                ("validation_status", models.CharField(choices=[("pending", "Pending"), ("valid", "Valid format"), ("invalid", "Invalid format")], default="pending", max_length=20)),
                ("source_supported", models.BooleanField(db_index=True, default=False)),
                ("observed_at", models.DateTimeField(default=timezone.now)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("lead", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="evidence", to="leads.lead")),
            ],
            options={"ordering": ["field_name", "-observed_at"]},
        ),
        migrations.RunPython(backfill_identities, migrations.RunPython.noop),
        migrations.AddConstraint(model_name="lead", constraint=models.UniqueConstraint(condition=~Q(normalized_url=""), fields=("normalized_url",), name="unique_lead_normalized_url")),
        migrations.AddConstraint(model_name="contact", constraint=models.UniqueConstraint(condition=~Q(normalized_email=""), fields=("client", "normalized_email"), name="unique_contact_email_per_client")),
        migrations.AddConstraint(model_name="contact", constraint=models.UniqueConstraint(condition=~Q(normalized_profile_url=""), fields=("client", "normalized_profile_url"), name="unique_contact_profile_per_client")),
        migrations.AddConstraint(model_name="leadevidence", constraint=models.UniqueConstraint(fields=("lead", "evidence_hash"), name="unique_lead_field_evidence")),
    ]
