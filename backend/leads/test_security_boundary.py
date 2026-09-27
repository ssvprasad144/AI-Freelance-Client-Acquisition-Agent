from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import (
    AcquisitionOpportunity,
    Client,
    FollowUp,
    Lead,
    LeadAnalysis,
    Outreach,
    Proposal,
    RevenueRecord,
)


class SingleOwnerSecurityBoundaryTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="owner-a", password="pass1234")
        self.other = User.objects.create_user(username="owner-b", password="pass1234")
        self.api = APIClient()

        self.lead = Lead.objects.create(
            owner=self.owner,
            title="Private Django opportunity",
            description="Private opportunity data.",
            company="Private Co",
            source="direct",
            source_url="https://private.example/opportunity/1",
            action_url="https://private.example/apply/1",
            contact_info={"email": "private@example.com"},
            status="qualified",
        )
        self.analysis = LeadAnalysis.objects.create(
            lead=self.lead,
            relevant=True,
            match_score=90,
            confidence=90,
            service_match="Django",
        )
        self.client_record = Client.objects.create(
            owner=self.owner,
            company="Private Co",
            normalized_company="private co",
        )
        self.lead.client = self.client_record
        self.lead.save(update_fields=["client", "updated_at"])
        self.proposal = Proposal.objects.create(lead=self.lead)
        self.outreach = Outreach.objects.create(
            lead=self.lead,
            proposal=self.proposal,
            medium="email",
            channel="email",
            message="Private message",
            status="draft",
        )
        self.followup = FollowUp.objects.create(
            lead=self.lead,
            scheduled_at=timezone.now() + timedelta(days=1),
            message="Private follow-up",
            status="draft",
        )
        self.opportunity = AcquisitionOpportunity.objects.create(
            lead=self.lead,
            recommended_action="generate_proposal",
        )
        self.revenue = RevenueRecord.objects.create(
            lead=self.lead,
            quoted_value=1000,
        )

    def authenticate_other(self):
        self.api.force_authenticate(self.other)

    def test_other_owner_cannot_read_or_mutate_lead(self):
        self.authenticate_other()
        self.assertEqual(self.api.get(f"/api/leads/{self.lead.id}/").status_code, 404)
        self.assertEqual(
            self.api.post(f"/api/leads/{self.lead.id}/set_status/", {"status": "won"}).status_code,
            404,
        )

    def test_other_owner_cannot_access_private_business_objects(self):
        self.authenticate_other()
        endpoints = [
            f"/api/proposals/{self.proposal.id}/",
            f"/api/followups/{self.followup.id}/send/",
            f"/api/outreach/{self.outreach.id}/send/",
            f"/api/clients/{self.client_record.id}/",
            f"/api/acquisition/{self.opportunity.id}/action/",
        ]
        for endpoint in endpoints:
            with self.subTest(endpoint=endpoint):
                response = self.api.get(endpoint) if endpoint.endswith("/") and "proposals/" in endpoint else self.api.post(endpoint)
                self.assertIn(response.status_code, {404, 405, 409})

        self.assertEqual(
            self.api.get(f"/api/revenue/records/?lead={self.lead.id}").status_code,
            200,
        )
        self.assertFalse(
            any(row["id"] == self.revenue.id for row in self.api.get("/api/revenue/records/").data["results"])
        )

    @patch("leads.views.send_email")
    def test_other_owner_cannot_claim_private_outreach(self, send_email):
        self.authenticate_other()
        response = self.api.post(f"/api/outreach/{self.outreach.id}/send/")
        self.assertEqual(response.status_code, 404)
        send_email.assert_not_called()
        self.outreach.refresh_from_db()
        self.assertEqual(self.outreach.status, "draft")

    @patch("leads.views.send_followup_email")
    def test_other_owner_cannot_claim_private_followup(self, send_email):
        self.followup.status = "due"
        self.followup.save(update_fields=["status"])
        self.authenticate_other()
        response = self.api.post(f"/api/followups/{self.followup.id}/send/")
        self.assertEqual(response.status_code, 404)
        send_email.assert_not_called()
        self.followup.refresh_from_db()
        self.assertEqual(self.followup.status, "due")
