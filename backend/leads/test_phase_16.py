from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from .models import Lead, LeadAnalysis, AcquisitionOpportunity
from .acquisition_orchestrator import opportunity_score, next_action, ensure_opportunity, VALID_ACTIONS
from .ai_service import _validated_analysis, _validated_proposal

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
    def test_plan_outreach_action_is_executable(self):
        self.assertIn("plan_outreach", VALID_ACTIONS)
        self.assertEqual(VALID_ACTIONS["plan_outreach"]["from"], ["proposal"])

    def test_queue_api(self):
        obj=ensure_opportunity(self.lead)
        response=self.api.get("/api/acquisition/queue/")
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.data[0]["id"],obj.id)

    def test_ai_output_validation(self):
        data={"relevant":True,"match_score":101,"service_match":"AI","requirements":[],"pain_points":[],"recommended_approach":"Scope first.","matching_projects":[],"confidence":-4}
        validated=_validated_analysis(data)
        self.assertEqual(validated["match_score"],100)
        self.assertEqual(validated["confidence"],0)
        with self.assertRaises(ValueError): _validated_analysis({"relevant":True})
        self.assertEqual(_validated_proposal("  proposal  "),"proposal")
        with self.assertRaises(ValueError): _validated_proposal("")

    def test_terminal_lead_not_queued(self):
        self.lead.status="won"; self.lead.save(update_fields=["status","updated_at"])
        response=self.api.get("/api/acquisition/queue/")
        self.assertEqual(response.status_code,200)
        self.assertEqual(len(response.data),0)
