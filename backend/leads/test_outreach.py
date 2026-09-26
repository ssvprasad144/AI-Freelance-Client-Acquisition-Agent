from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Lead, LeadAnalysis, Outreach


class SourceAwareOutreachTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="outreach-test", password="pass1234")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def make_lead(self, source, **kwargs):
        return Lead.objects.create(
            title="Django developer needed",
            description="Build a Django API and dashboard.",
            source=source,
            source_url=kwargs.get("source_url", "https://example.com/opportunity/123"),
            action_url=kwargs.get("action_url", "https://example.com/apply/123"),
            company="Example Co",
            technologies=["Django", "PostgreSQL"],
            contact_info=kwargs.get("contact_info", {}),
        )

    def qualify(self, lead):
        return LeadAnalysis.objects.create(
            lead=lead, relevant=True, match_score=90, service_match="Full-Stack Development",
            requirements=["Django"], pain_points=["Needs a backend"],
            recommended_approach="Build the API first.", matching_projects=["CareerInnTech"], confidence=90,
        )

    def test_marketplace_proposal_keeps_exact_action_url(self):
        lead = self.make_lead("freelancer", action_url="https://www.freelancer.com/projects/django/123")
        self.qualify(lead)
        response = self.client.post(f"/api/leads/{lead.id}/proposal/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["medium"], "marketplace_bid")
        self.assertEqual(response.data["destination_url"], "https://www.freelancer.com/projects/django/123")
        self.assertFalse(response.data["can_send"])

    def test_linkedin_proposal_can_be_opened_and_marked_submitted(self):
        lead = self.make_lead("linkedin", action_url="https://www.linkedin.com/in/example")
        self.qualify(lead)
        response = self.client.post(f"/api/leads/{lead.id}/proposal/")
        outreach_id = response.data["outreach_id"]
        opened = self.client.post(f"/api/outreach/{outreach_id}/open/")
        self.assertEqual(opened.status_code, 200)
        self.assertEqual(opened.data["status"], "opened")
        submitted = self.client.post(f"/api/outreach/{outreach_id}/mark-submitted/")
        self.assertEqual(submitted.status_code, 200)
        self.assertEqual(submitted.data["status"], "submitted")
        lead.refresh_from_db()
        self.assertEqual(lead.status, "contacted")

    def test_email_proposal_is_sendable_only_after_approval(self):
        lead = self.make_lead("direct", contact_info={"email": "client@example.com"})
        self.qualify(lead)
        response = self.client.post(f"/api/leads/{lead.id}/proposal/")
        self.assertEqual(response.data["medium"], "email")
        self.assertTrue(response.data["can_send"])
        outreach = Outreach.objects.get(pk=response.data["outreach_id"])
        self.assertEqual(outreach.status, "draft")
        approved = self.client.post(f"/api/leads/{lead.id}/approve_proposal/")
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(approved.data["status"], "approved")
