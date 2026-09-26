from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from .models import Lead, LeadAnalysis, AcquisitionOpportunity
from .acquisition_orchestrator import opportunity_score, next_action, ensure_opportunity, execute_action

class Phase16Tests(TestCase):
    def setUp(self):
        self.api=APIClient(); user=get_user_model().objects.create_user(username="p16",password="pass123"); self.api.force_authenticate(user)
        self.lead=Lead.objects.create(title="AI dashboard",description="Django React AI automation",source="direct",lead_type="direct",budget_text="$5000",technologies=["Django","React"])
    def test_scoring_and_next_action(self):
        self.assertGreaterEqual(opportunity_score(self.lead),20)
        self.assertEqual(next_action(self.lead)["action"],"qualify")
        LeadAnalysis.objects.create(lead=self.lead,relevant=True,match_score=85,confidence=90)
        self.lead.status="qualified"; self.lead.save(update_fields=["status","updated_at"])
        self.assertEqual(next_action(self.lead)["action"],"generate_proposal")
    def test_queue_api(self):
        obj=ensure_opportunity(self.lead)
        response=self.api.get("/api/acquisition/queue/")
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.data[0]["id"],obj.id)
    def test_approval_then_real_proposal_execution(self):
        analysis=LeadAnalysis.objects.create(lead=self.lead,relevant=True,match_score=85,confidence=90)
        self.lead.status="qualified"; self.lead.save(update_fields=["status","updated_at"])
        obj=ensure_opportunity(self.lead)
        obj.recommended_action="generate_proposal"; obj.save(update_fields=["recommended_action"])
        pending=execute_action(obj,"generate_proposal",approved=False)
        self.assertTrue(pending["requires_approval"])
        obj.refresh_from_db()
        result=execute_action(obj,"generate_proposal",approved=True)
        self.assertTrue(result["executed"])
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.status,"proposal")
        self.assertTrue(self.lead.proposals.exists())

    def test_stale_action_is_rejected(self):
        LeadAnalysis.objects.create(lead=self.lead,relevant=True,match_score=85,confidence=90)
        self.lead.status="qualified"; self.lead.save(update_fields=["status","updated_at"])
        obj=ensure_opportunity(self.lead)
        obj.recommended_action="approve_proposal"; obj.save(update_fields=["recommended_action"])
        with self.assertRaises(ValueError):
            execute_action(obj,"approve_proposal",approved=True)

    def test_terminal_lead_not_queued(self):
        self.lead.status="won"; self.lead.save(update_fields=["status","updated_at"])
        response=self.api.get("/api/acquisition/queue/")
        self.assertEqual(response.status_code,200)
        self.assertEqual(len(response.data),0)
