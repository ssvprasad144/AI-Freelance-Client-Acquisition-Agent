from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import FollowUp, FollowUpSequence, Lead, LeadAnalysis, Proposal, ProposalVersion


class Phase710Tests(TestCase):
    def setUp(self):
        self.client=APIClient()
        user=get_user_model().objects.create_user(username="phase710",password="pass1234")
        self.client.force_authenticate(user)
        self.lead=Lead.objects.create(
            title="Django AI automation dashboard",
            description="Build a Django AI automation dashboard.",
            source="freelancer",
            source_url="https://example.com/project/1",
            action_url="https://example.com/bid/1",
            technologies=["Django","AI"],
            company="Example Co",
        )
        LeadAnalysis.objects.create(
            lead=self.lead,relevant=True,match_score=90,service_match="AI Products",
            requirements=["Django"],pain_points=["Automation"],recommended_approach="Build the workflow first.",
            matching_projects=["CareerInnTech"],confidence=90,
        )

    def test_proposal_creates_version_and_workspace(self):
        response=self.client.post(f"/api/leads/{self.lead.id}/proposal/")
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.data["version"],1)
        proposal=Proposal.objects.get(pk=response.data["proposal_id"])
        self.assertEqual(proposal.versions.count(),1)
        workspace=self.client.get(f"/api/proposals/{proposal.id}/")
        self.assertEqual(workspace.status_code,200)
        self.assertEqual(workspace.data["current_version"],1)

    def test_proposal_edit_creates_new_version(self):
        proposal,_=__import__("leads.proposal_service",fromlist=["create_proposal"]).create_proposal(
            self.lead,self.lead.analysis,"marketplace_bid"
        )
        response=self.client.put(f"/api/proposals/{proposal.id}/edit/",{"content":"Edited proposal."},format="json")
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.data["current_version"],2)
        self.assertEqual(ProposalVersion.objects.get(proposal=proposal,version_number=2).source,"user")

    def test_reply_classification_is_persisted(self):
        response=self.client.post(
            f"/api/leads/{self.lead.id}/replies/",
            {"message":"Thanks, let's schedule a call next week.","channel":"email"},
            format="json",
        )
        self.assertEqual(response.status_code,201)
        self.assertEqual(response.data["classification"]["next_action"],"schedule_call")
        reply=self.lead.replies.get()
        self.assertEqual(reply.next_action,"schedule_call")

    def test_followup_sequence_creates_reviewable_draft(self):
        response=self.client.post(f"/api/leads/{self.lead.id}/followup-sequence/",{"delays_days":[3,5,7],"max_steps":3},format="json")
        self.assertEqual(response.status_code,201)
        sequence=FollowUpSequence.objects.get(pk=response.data["sequence"]["id"])
        followup=FollowUp.objects.get(sequence=sequence,step_number=1)
        self.assertEqual(followup.status,"draft")
        self.assertEqual(sequence.delays_days,[3,5,7])

    def test_reply_stops_sequence(self):
        sequence=FollowUpSequence.objects.create(lead=self.lead,max_steps=3,delays_days=[3,5,7],current_step=1)
        FollowUp.objects.create(sequence=sequence,lead=self.lead,step_number=1,scheduled_at=timezone.now()+timedelta(days=3),message="draft")
        self.client.post(f"/api/leads/{self.lead.id}/replies/",{"message":"Not interested.","channel":"email"},format="json")
        from .followup_intelligence import cancel_if_stopped
        sequence.refresh_from_db()
        self.assertTrue(cancel_if_stopped(sequence))
        self.assertEqual(sequence.status,"completed")
        self.assertEqual(sequence.followups.first().status,"cancelled")


    def test_followup_sequence_rejects_malformed_delays(self):
        response=self.client.post(
            f"/api/leads/{self.lead.id}/followup-sequence/",
            {"delays_days":["not-a-number"],"max_steps":3},
            format="json",
        )
        self.assertEqual(response.status_code,400)
