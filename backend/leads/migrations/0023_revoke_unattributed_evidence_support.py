from django.db import migrations


def revoke_unattributed_evidence_support(apps, schema_editor):
    """Legacy rows predate URL-bound Responses citations and cannot be verified."""
    LeadEvidence = apps.get_model("leads", "LeadEvidence")
    LeadEvidence.objects.filter(source_supported=True).update(source_supported=False)


class Migration(migrations.Migration):
    dependencies = [("leads", "0022_discoveryquerycache_source_findings")]

    operations = [
        migrations.RunPython(revoke_unattributed_evidence_support, migrations.RunPython.noop),
    ]
