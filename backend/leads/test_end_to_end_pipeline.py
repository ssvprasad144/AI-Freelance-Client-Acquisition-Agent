from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import AcquisitionOpportunity, FollowUp, FollowUpSequence, Lead


class EndToEndPipelineTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="pipeline-owner", password="pass12345")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    @patch("leads.discovery_cycle.DiscoveryService.discover")
    @patch("leads.discovery_cycle.analyze_lead")
    def test_discovery_creates_owner_scoped_opportunity_for_qualified_lead(self, analyze, discover):
        discover.return_value = {
            "source": "mock",
            "model": "test",
            "leads": [{
                "title": "Django automation project",
                "description": "Build a Django API and automation platform.",
                "source_url": "https://example.com/projects/1",
                "company": "Example Co",
                "source": "direct",
                "technologies": ["Django", "Python"],
            }],
        }
        analyze.return_value = {
            "relevant": True,
            "match_score": 95,
            "confidence": 95,
            "service_match": "Django",
            "recommended_approach": "Build the API in milestones.",
            "matching_projects": [],
            "model": "test",
        }
        from .discovery_cycle import run_discovery_cycle
        result = run_discovery_cycle(
            query="Django automation",
            source="live",
            qualification_limit=5,
            profile_id="test-profile",
            owner=self.user,
        )
        self.assertEqual(result["qualified"], 1)
        lead = Lead.objects.get(owner=self.user, title="Django automation project")
        self.assertTrue(AcquisitionOpportunity.objects.filter(lead=lead).exists())
        self.assertEqual(AcquisitionOpportunity.objects.get(lead=lead).recommended_action, "generate_proposal")

    def test_terminal_status_cancels_pending_followups(self):
        lead = Lead.objects.create(owner=self.user, title="Terminal", description="Test", source_url="https://example.com/terminal")
        sequence = FollowUpSequence.objects.create(lead=lead, status="active", max_steps=2, delays_days=[3, 5])
        FollowUp.objects.create(
            lead=lead, sequence=sequence,
            scheduled_at=timezone.now() + timedelta(days=1),
            message="Draft", status="approved",
        )
        response = self.client.post(f"/api/leads/{lead.id}/set_status/", {"status": "won"})
        self.assertEqual(response.status_code, 200)
        sequence.refresh_from_db()
        self.assertEqual(sequence.status, "completed")
        self.assertEqual(FollowUp.objects.get(sequence=sequence).status, "cancelled")

    @patch("leads.discovery_cycle.DiscoveryService.discover")
    def test_discovery_rejects_unsafe_source_urls(self, discover):
        discover.return_value = {
            "source": "live", "model": "test",
            "leads": [{
                "title": "Private target",
                "description": "Should never be stored.",
                "source_url": "http://127.0.0.1/admin",
            }],
        }
        from .discovery_cycle import run_discovery_cycle
        result = run_discovery_cycle(query="unsafe", source="live", qualification_limit=5, profile_id="test-profile", owner=self.user)
        self.assertEqual(result["created"], 0)
        self.assertEqual(result["invalid"], 1)
        self.assertFalse(Lead.objects.filter(owner=self.user, title="Private target").exists())
