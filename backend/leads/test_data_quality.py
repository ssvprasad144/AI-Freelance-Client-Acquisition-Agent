from datetime import timedelta
import importlib
from django.apps import apps
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone
from unittest.mock import patch

from .acquisition import send_email
from .client_service import _validated_client_intelligence, sync_lead_client
from .data_quality import normalize_url, validate_discovered_email, validate_lead_record
from .discovery_cycle import _fresh_qualified_inventory, _store
from .models import ActivityLog, Client, Contact, Lead, LeadEvidence, Outreach


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
        findings = [{"url": "https://acme.test/jobs/42", "excerpt": "Acme Labs seeks a Django engineer."}]
        row = lead_row()
        row["evidence"] = [
            {"field": "company", "value": "Acme Labs", "source_url": "https://acme.test/jobs/42", "excerpt": "Acme Labs seeks a Django engineer."},
            {"field": "location", "value": "London", "source_url": "https://acme.test/jobs/42", "excerpt": "New York role"},
            {"field": "company", "value": "Acme Labs", "source_url": "https://other.test/job", "excerpt": "Acme Labs seeks a Django engineer."},
        ]
        cleaned = validate_lead_record(row, findings)
        self.assertEqual([e["field"] for e in cleaned["evidence"]], ["company"])

    def test_evidence_from_a_different_source_url_is_rejected(self):
        row = lead_row()
        row["evidence"] = [{"field": "company", "value": "Acme Labs", "source_url": "https://acme.test/jobs/42", "excerpt": "Acme Labs seeks a Django engineer."}]
        findings = [{"url": "https://other.test/jobs/9", "excerpt": "Acme Labs seeks a Django engineer."}]
        with self.assertRaisesMessage(ValueError, "source_url is not supported"):
            validate_lead_record(row, findings)

    def test_combined_or_missing_findings_can_never_support_evidence(self):
        row = lead_row()
        row["evidence"] = [{"field": "company", "value": "Acme Labs", "source_url": "https://acme.test/jobs/42", "excerpt": "Acme Labs seeks a Django engineer."}]
        self.assertEqual(validate_lead_record(row, "Acme Labs seeks a Django engineer. https://acme.test/jobs/42")["evidence"], [])
        with self.assertRaisesMessage(ValueError, "source_url is not supported"):
            validate_lead_record(row, [])
        with self.assertRaisesMessage(ValueError, "source_url is not supported"):
            validate_lead_record(row, [{"url": "not a URL", "excerpt": "Acme Labs seeks a Django engineer."}])

    def test_empty_evidence_source_url_can_never_support_evidence(self):
        row = lead_row()
        row["evidence"] = [{"field": "company", "value": "Acme Labs", "source_url": "", "excerpt": "Acme Labs seeks a Django engineer."}]
        findings = [{"url": "https://acme.test/jobs/42", "excerpt": "Acme Labs seeks a Django engineer."}]
        self.assertEqual(validate_lead_record(row, findings)["evidence"], [])

    def test_lead_source_url_must_be_a_url_bound_source_finding(self):
        row = lead_row()
        findings = [{"url": "https://other.test/jobs/9", "excerpt": "A Django role."}]
        with self.assertRaisesMessage(ValueError, "source_url is not supported"):
            validate_lead_record(row, findings)

    def test_evidence_from_its_specific_source_url_is_accepted(self):
        row = lead_row()
        row["evidence"] = [{"field": "company", "value": "Acme Labs", "source_url": "https://acme.test/jobs/42", "excerpt": "Acme Labs seeks a Django engineer."}]
        findings = [{"url": "https://acme.test/jobs/42", "excerpt": "Acme Labs seeks a Django engineer."}]
        self.assertEqual(validate_lead_record(row, findings)["evidence"][0]["source_url"], "https://acme.test/jobs/42")

    def test_source_url_normalization_only_accepts_equivalent_destinations(self):
        row = lead_row("https://www.acme.test/jobs/42/?utm_source=search#apply")
        row["evidence"] = [{"field": "source_url", "value": "https://www.acme.test/jobs/42", "source_url": "https://www.acme.test/jobs/42/?utm_source=search#apply", "excerpt": "Apply at https://www.acme.test/jobs/42"}]
        equivalent = [{"url": "https://www.acme.test:443/jobs/42/", "excerpt": "Apply at https://www.acme.test/jobs/42"}]
        self.assertEqual(validate_lead_record(row, equivalent)["evidence"][0]["source_url"], "https://www.acme.test/jobs/42")

        different_scheme = [{"url": "http://www.acme.test/jobs/42", "excerpt": "Apply at https://www.acme.test/jobs/42"}]
        with self.assertRaisesMessage(ValueError, "source_url is not supported"):
            validate_lead_record(row, different_scheme)

        different_host = [{"url": "https://acme.test/jobs/42", "excerpt": "Apply at https://www.acme.test/jobs/42"}]
        with self.assertRaisesMessage(ValueError, "source_url is not supported"):
            validate_lead_record(row, different_host)

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
        findings = [{"url": "https://acme.test/jobs/42", "excerpt": "Other Co seeks a Django engineer."}]
        existing = lead_row()
        self.assertEqual(_store([existing], search_findings=""), (1, 0, 0))
        conflict = lead_row()
        conflict["company"] = "Other Co"
        conflict["evidence"] = [{"field": "company", "value": "Other Co", "source_url": "https://acme.test/jobs/42", "excerpt": "Other Co seeks a Django engineer."}]
        self.assertEqual(_store([conflict], source_findings=findings, source_checked=True), (0, 1, 0))
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
        source_findings = [{"url": "https://acme.com/jobs/42", "excerpt": "A Django role."}]
        cache = DiscoveryQueryCache.objects.create(query="Django", normalized_query="django", search_findings="A Django role. https://acme.com/jobs/42", source_findings=source_findings)
        self.assertIn("https://acme.com/jobs/42", cache.search_findings)
        self.assertEqual(cache.source_findings, source_findings)

    @patch("leads.discovery_cycle.analyze_lead")
    @patch("leads.discovery_cycle.DiscoveryService.discover")
    def test_cache_replay_uses_persisted_source_findings(self, discover, analyze):
        row = lead_row("https://acme.test/jobs/42")
        row["evidence"] = [{"field": "company", "value": "Acme Labs", "source_url": "https://acme.test/jobs/42", "excerpt": "Acme Labs needs a Django engineer."}]
        from .models import DiscoveryQueryCache
        DiscoveryQueryCache.objects.create(
            query="Django freelance",
            normalized_query="django freelance",
            profile_id="cache-test",
            searched_at=timezone.now(),
            result_payload=[row],
            source_findings=[{"url": "https://acme.test/jobs/42", "excerpt": "Acme Labs needs a Django engineer."}],
        )
        from .discovery_cycle import run_discovery_cycle
        run_discovery_cycle(query="Django freelance", profile_id="cache-test")
        self.assertFalse(discover.called)
        self.assertTrue(LeadEvidence.objects.filter(field_name="company", value="Acme Labs", source_supported=True).exists())

    @patch("leads.discovery_cycle.analyze_lead")
    @patch("leads.discovery_cycle.DiscoveryService.discover")
    def test_cache_replay_cannot_use_legacy_combined_findings(self, discover, analyze):
        row = lead_row("https://acme.test/jobs/42")
        row["evidence"] = [{"field": "company", "value": "Acme Labs", "source_url": "https://acme.test/jobs/42", "excerpt": "Acme Labs needs a Django engineer."}]
        from .models import DiscoveryQueryCache
        DiscoveryQueryCache.objects.create(
            query="Django freelance",
            normalized_query="django freelance",
            profile_id="legacy-cache-test",
            searched_at=timezone.now(),
            result_payload=[row],
            search_findings="Acme Labs needs a Django engineer. https://acme.test/jobs/42",
        )
        from .discovery_cycle import run_discovery_cycle
        run_discovery_cycle(query="Django freelance", profile_id="legacy-cache-test")
        self.assertFalse(discover.called)
        self.assertFalse(LeadEvidence.objects.filter(field_name="company", value="Acme Labs", source_supported=True).exists())

    def test_legacy_evidence_migration_revokes_existing_support(self):
        lead = Lead.objects.create(title="Legacy", description="Django", source_url="https://acme.test/jobs/legacy")
        evidence = LeadEvidence.objects.create(
            lead=lead,
            field_name="company",
            value="Acme Labs",
            source_url="https://acme.test/jobs/legacy",
            evidence_hash="legacy-evidence",
            source_supported=True,
        )
        migration = importlib.import_module("leads.migrations.0023_revoke_unattributed_evidence_support")
        migration.revoke_unattributed_evidence_support(apps, None)
        evidence.refresh_from_db()
        self.assertFalse(evidence.source_supported)

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
        row["evidence"] = [{"field": "company_website", "value": "https://official.acme.com", "source_url": "https://acme.com/jobs/42", "excerpt": "Acme official website: https://official.acme.com"}]
        findings = [
            {"url": "https://acme.com/jobs/42", "excerpt": "Django automation role."},
            {"url": "https://other.test/jobs/9", "excerpt": "Acme official website: https://official.acme.com"},
        ]
        self.assertEqual(_store([row], source_findings=findings), (1, 0, 0))
        lead = Lead.objects.get(normalized_url="https://acme.com/jobs/42")
        client, _ = sync_lead_client(lead)
        self.assertEqual(client.domain, "")

    def test_unsupported_contact_email_is_not_eligible_for_automated_email(self):
        row = lead_row()
        row["contact_info"] = {"email": "sales@acme-labs.com"}
        row["evidence"] = [{"field": "contact_info.email", "value": "sales@acme-labs.com", "source_url": "https://acme.test/jobs/42", "excerpt": "Email sales@acme-labs.com"}]
        findings = [
            {"url": "https://acme.test/jobs/42", "excerpt": "Django automation role."},
            {"url": "https://other.test/jobs/9", "excerpt": "Email sales@acme-labs.com"},
        ]
        self.assertEqual(_store([row], source_findings=findings), (1, 0, 0))
        lead = Lead.objects.get()
        self.assertFalse(lead.evidence.filter(field_name="contact_info.email", source_supported=True).exists())
        outreach = Outreach.objects.create(lead=lead, message="Hello", status="approved")
        with self.assertRaisesMessage(ValueError, "no supporting source evidence"):
            send_email(outreach)


class LegacyIdentitySaveTests(TestCase):
    def test_legacy_duplicate_lead_key_stays_blank_on_unrelated_edit(self):
        row = lead_row()
        row.pop("evidence", None)
        lead = Lead.objects.create(**row)
        Lead.objects.filter(pk=lead.pk).update(normalized_url="")
        lead.refresh_from_db()
        lead.description = "Updated description."
        lead.save()
        lead.refresh_from_db()
        self.assertEqual(lead.normalized_url, "")

    def test_legacy_duplicate_contact_keys_stay_blank_on_unrelated_edit(self):
        client = Client.objects.create(company="Acme", normalized_company="acme")
        contact = Contact.objects.create(client=client, email="person@acme.com", profile_url="https://acme.test/person")
        Contact.objects.filter(pk=contact.pk).update(normalized_email="", normalized_profile_url="")
        contact.refresh_from_db()
        contact.name = "Updated Name"
        contact.save()
        contact.refresh_from_db()
        self.assertEqual(contact.normalized_email, "")
        self.assertEqual(contact.normalized_profile_url, "")
