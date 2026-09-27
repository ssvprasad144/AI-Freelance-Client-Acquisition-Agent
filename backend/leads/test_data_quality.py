from datetime import timedelta
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from .client_service import _validated_client_intelligence, sync_lead_client
from .data_quality import normalize_url, validate_discovered_email, validate_lead_record
from .discovery_cycle import _fresh_qualified_inventory, _store
from .models import ActivityLog, Client, Contact, Lead, LeadEvidence


def lead_row(url="https://acme.test/jobs/42"):
    return {
        "title": "Django Automation Engineer",
        "company": "Acme Labs",
        "description": "Build a Django automation workflow for the client.",
        "source": "web_search",
        "source_url": url,
        "action_url": url,
        "lead_type": "freelance",
        "budget_text": "",
        "technologies": ["Django"],
        "contact_info": {},
        "evidence": [],
    }


class LeadDataQualityTests(TestCase):
    def test_url_validation_and_canonicalization(self):
        self.assertEqual(normalize_url("HTTPS://WWW.Acme.com:443/jobs/42/?utm_source=mail#apply"), "https://www.acme.com/jobs/42")
        for url in ("javascript:alert(1)", "https://", "http://localhost/admin", "https://user:pass@acme.com/x", "https://acme.com/a b"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                normalize_url(url)

    def test_email_validation_distinguishes_format_from_source_verification(self):
        self.assertEqual(validate_discovered_email(" SALES@Acme.com "), "sales@acme.com")
        for email in ("not-an-email", "person@example.com", "person@placeholder.test"):
            with self.subTest(email=email), self.assertRaises(ValueError):
                validate_discovered_email(email)

    def test_evidence_requires_cited_url_literal_excerpt_and_claim(self):
        findings = "Acme Labs seeks a Django engineer. https://acme.test/jobs/42"
        row = lead_row()
        row["evidence"] = [
            {"field": "company", "value": "Acme Labs", "source_url": "https://acme.test/jobs/42", "excerpt": "Acme Labs seeks a Django engineer."},
            {"field": "location", "value": "London", "source_url": "https://acme.test/jobs/42", "excerpt": "New York role"},
            {"field": "company", "value": "Acme Labs", "source_url": "https://other.test/job", "excerpt": "Acme Labs seeks a Django engineer."},
        ]
        cleaned = validate_lead_record(row, findings)
        self.assertEqual([e["field"] for e in cleaned["evidence"]], ["company"])

    def test_partial_batch_failure_keeps_valid_record_and_logs_rejection(self):
        invalid = lead_row("file:///etc/passwd")
        created, duplicates, rejected = _store([invalid, lead_row("https://acme.test/jobs/42")], search_findings="")
        self.assertEqual((created, duplicates, rejected), (1, 0, 1))
        self.assertEqual(Lead.objects.count(), 1)
        self.assertTrue(ActivityLog.objects.filter(event_type="discovery.record_rejected").exists())

    def test_canonical_duplicate_is_rejected_by_application_and_database(self):
        self.assertEqual(_store([lead_row("https://acme.test/jobs/42?utm_campaign=x"), lead_row("https://acme.test/jobs/42")]), (1, 1, 0))
        lead = Lead.objects.get()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Lead.objects.create(title="Concurrent copy", normalized_url=lead.normalized_url, source_url=lead.source_url, description="Another row")

    def test_conflicting_source_claim_is_preserved_without_overwriting_current_lead(self):
        findings = "Other Co seeks a Django engineer. https://acme.test/jobs/42"
        existing = lead_row()
        self.assertEqual(_store([existing], search_findings=""), (1, 0, 0))
        conflict = lead_row()
        conflict["company"] = "Other Co"
        conflict["evidence"] = [{"field": "company", "value": "Other Co", "source_url": "https://acme.test/jobs/42", "excerpt": "Other Co seeks a Django engineer."}]
        self.assertEqual(_store([conflict], search_findings=findings, source_checked=True), (0, 1, 0))
        lead = Lead.objects.get()
        self.assertEqual(lead.company, "Acme Labs")
        self.assertTrue(LeadEvidence.objects.filter(lead=lead, field_name="company", value="Other Co", source_supported=True).exists())

    def test_cached_replay_does_not_mark_lead_verified_or_checked(self):
        stale = timezone.now() - timedelta(days=60)
        self.assertEqual(_store([lead_row()], search_findings=""), (1, 0, 0))
        lead = Lead.objects.get()
        lead.last_verified_at = stale
        lead.save(update_fields=["last_verified_at"])
        _store([lead_row()], search_findings="", source_checked=False)
        lead.refresh_from_db()
        self.assertEqual(lead.last_verified_at, stale)
        self.assertIsNone(lead.last_checked_at)

    def test_discovery_cache_keeps_source_findings_for_later_evidence_validation(self):
        from .models import DiscoveryQueryCache
        cache = DiscoveryQueryCache.objects.create(query="Django", normalized_query="django", search_findings="A Django role. https://acme.com/jobs/42")
        self.assertIn("https://acme.com/jobs/42", cache.search_findings)

    def test_company_and_contact_identity_are_conservatively_deduplicated(self):
        row = lead_row()
        row["contact_info"] = {"name": "Jane Doe", "email": "JANE@ACME-LABS.COM", "profile_url": "https://profiles.acme.test/jane"}
        _store([row])
        _store([row])
        first = Lead.objects.first()
        second_row = lead_row("https://acme.test/jobs/43")
        second_row["title"] = "Different contract"
        second_row["contact_info"] = {"name": "Jane", "email": "jane@acme-labs.com", "profile_url": "https://profiles.acme.test/jane/"}
        _store([second_row])
        second = Lead.objects.get(normalized_url="https://acme.test/jobs/43")
        client1, contact1 = sync_lead_client(first)
        client2, contact2 = sync_lead_client(second)
        self.assertEqual(client1.pk, client2.pk)
        self.assertEqual(contact1.pk, contact2.pk)
        self.assertEqual(Client.objects.count(), 1)
        self.assertEqual(Contact.objects.count(), 1)

    def test_database_contact_identity_guard(self):
        client = Client.objects.create(company="Acme", normalized_company="acme")
        Contact.objects.create(client=client, email="person@acme.com")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Contact.objects.create(client=client, email="PERSON@ACME.COM")

    def test_stale_unverified_qualified_lead_is_not_counted_as_fresh_inventory(self):
        Lead.objects.create(title="Old", description="Django", source_url="https://stale.test/job", status="qualified", last_verified_at=timezone.now()-timedelta(days=30))
        self.assertEqual(_fresh_qualified_inventory(), 0)

    def test_malformed_ai_structure_and_invalid_values_are_rejected(self):
        with self.assertRaises(ValueError):
            _validated_client_intelligence({"summary": "only partial"})
        with self.assertRaises(ValueError):
            _validated_client_intelligence({"summary": "x", "communication_style": "neutral", "preferences": [], "objections": [], "recommended_approach": "x", "confidence": 101})

    def test_non_source_supported_company_website_does_not_assign_client_domain(self):
        row = lead_row("https://acme.com/jobs/42")
        row["company_website"] = "https://official.acme.com"
        self.assertEqual(_store([row]), (1, 0, 0))
        lead = Lead.objects.get(normalized_url="https://acme.com/jobs/42")
        client, _ = sync_lead_client(lead)
        self.assertEqual(client.domain, "")
