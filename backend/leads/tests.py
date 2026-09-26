from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from .models import ActivityLog,FollowUp,Lead,LeadAnalysis,Outreach,Reply
from .analytics import acquisition_metrics

class APITestBase(TestCase):
    def setUp(self):
        self.client=APIClient()
        self.user=get_user_model().objects.create_user(username="testuser",password="testpass123")
        self.client.force_authenticate(self.user)
        self.lead=Lead.objects.create(title="Django Automation Engineer",description="Build a Django automation workflow.",source_url="https://example.com/jobs/1")

class AuthTests(TestCase):
    def test_protected_endpoint_requires_auth(self):
        self.assertEqual(APIClient().get("/api/dashboard/").status_code,401)
    def test_login_returns_token(self):
        get_user_model().objects.create_user(username="user",password="pass12345")
        response=APIClient().post("/api/auth/login/",{"username":"user","password":"pass12345"},format="json")
        self.assertEqual(response.status_code,200); self.assertTrue(response.data["token"])

class FollowUpLifecycleTests(APITestBase):
    def test_create_and_approve_followup(self):
        scheduled=timezone.now()+timedelta(hours=2)
        response=self.client.post("/api/followups/create/",{"lead_id":self.lead.id,"scheduled_at":scheduled.isoformat(),"message":"Following up on the opportunity."},format="json")
        self.assertEqual(response.status_code,200); followup=FollowUp.objects.get(pk=response.data["id"]); self.assertEqual(followup.status,"draft")
        response=self.client.post(f"/api/followups/{followup.id}/approve/",format="json")
        self.assertEqual(response.status_code,200); followup.refresh_from_db(); self.assertEqual(followup.status,"approved"); self.assertFalse(response.data["sent"])

    def test_due_processing_is_idempotent_and_never_sends(self):
        followup=FollowUp.objects.create(lead=self.lead,scheduled_at=timezone.now()-timedelta(minutes=5),message="Time to follow up.",status="approved")
        response=self.client.post("/api/followups/process-due/",format="json")
        self.assertEqual(response.status_code,200); self.assertEqual(response.data["processed"],1); self.assertFalse(response.data["sent"])
        followup.refresh_from_db(); self.assertEqual(followup.status,"due"); self.assertEqual(ActivityLog.objects.filter(event_type="followup.due").count(),1)
        response=self.client.post("/api/followups/process-due/",format="json"); self.assertEqual(response.data["processed"],0); self.assertEqual(ActivityLog.objects.filter(event_type="followup.due").count(),1)

    def test_future_approved_followup_is_not_due(self):
        FollowUp.objects.create(lead=self.lead,scheduled_at=timezone.now()+timedelta(hours=1),message="Future follow-up.",status="approved")
        self.client.post("/api/followups/process-due/",format="json")
        response=self.client.get("/api/followups/due/"); self.assertEqual(response.status_code,200); self.assertEqual(response.data["results"],[])

    def test_management_command_processes_due_followup(self):
        FollowUp.objects.create(lead=self.lead,scheduled_at=timezone.now()-timedelta(minutes=1),message="Worker follow-up.",status="approved")
        call_command("process_due_followups"); self.assertEqual(FollowUp.objects.filter(status="due").count(),1)

class LeadLifecycleTests(APITestBase):
    def test_status_and_reply(self):
        response=self.client.post(f"/api/leads/{self.lead.id}/set_status/",{"status":"contacted"},format="json")
        self.assertEqual(response.status_code,200); self.assertEqual(response.data["status"],"contacted")
        response=self.client.post(f"/api/leads/{self.lead.id}/replies/",{"message":"Thanks, let's discuss.","channel":"email"},format="json")
        self.assertEqual(response.status_code,201); self.lead.refresh_from_db(); self.assertEqual(self.lead.status,"replied"); self.assertEqual(Reply.objects.count(),1)

class DiscoveryWorkerTests(APITestBase):
    def _result(self):
        return {"source":"web_search","model":"gpt-4o-mini","leads":[{"title":"AI Automation Dashboard","company":"Example Client","description":"Build an AI-powered Django automation dashboard.","source":"web_search","source_url":"https://example.com/opportunities/automation","lead_type":"freelance","budget_text":"$1,000","technologies":["Django","AI"],"contact_info":{}}]}
    @patch("leads.discovery_cycle.analyze_lead")
    @patch("leads.discovery_cycle.DiscoveryService.discover")
    def test_discovery_worker_discovers_and_qualifies(self,discover,analyze):
        discover.return_value=self._result(); analyze.return_value={"relevant":True,"match_score":85,"service_match":"AI Products","requirements":["Django"],"pain_points":[],"recommended_approach":"Build the smallest useful workflow first.","matching_projects":["AI Business Automation Dashboard"],"confidence":90,"model":"gpt-4o-mini","input_tokens":10,"output_tokens":10}
        call_command("run_discovery_cycle","--source","live","--limit","5")
        self.assertEqual(Lead.objects.filter(title="AI Automation Dashboard").count(),1); self.assertEqual(Lead.objects.get(title="AI Automation Dashboard").status,"qualified")
        self.assertEqual(LeadAnalysis.objects.count(),1); self.assertEqual(ActivityLog.objects.filter(event_type="discovery.completed").count(),1)
    @patch("leads.discovery_cycle.analyze_lead")
    @patch("leads.discovery_cycle.DiscoveryService.discover")
    def test_discovery_worker_deduplicates_on_repeat_cycle(self,discover,analyze):
        discover.return_value=self._result(); analyze.return_value={"relevant":False,"match_score":20,"service_match":"Needs review","requirements":[],"pain_points":[],"recommended_approach":"Review manually.","matching_projects":[],"confidence":30,"model":"gpt-4o-mini","input_tokens":10,"output_tokens":10}
        call_command("run_discovery_cycle","--limit","5"); call_command("run_discovery_cycle","--limit","5")
        self.assertEqual(Lead.objects.filter(title="AI Automation Dashboard").count(),1); self.assertEqual(LeadAnalysis.objects.count(),1); self.assertEqual(analyze.call_count,1)


class AcquisitionEngineTests(APITestBase):
    def test_reply_is_classified_and_analytics_exposed(self):
        response=self.client.post(f"/api/leads/{self.lead.id}/replies/",{"message":"I am interested, can we schedule a call?","channel":"email"},format="json")
        self.assertEqual(response.status_code,201)
        self.assertEqual(response.data["classification"]["intent"],"interested")
        metrics=acquisition_metrics()
        self.assertEqual(metrics["funnel"]["replied"],1)
        self.assertEqual(self.client.get("/api/analytics/").status_code,200)

    def test_discovery_profiles_are_available(self):
        response=self.client.get("/api/discovery/profiles/")
        self.assertEqual(response.status_code,200)
        self.assertGreaterEqual(len(response.data["profiles"]),4)

    def test_approved_outreach_stays_blocked_without_explicit_enable(self):
        outreach=Outreach.objects.create(lead=self.lead,channel="email",message="Hello",status="approved")
        response=self.client.post(f"/api/outreach/{outreach.id}/send/",format="json")
        self.assertEqual(response.status_code,400)
        outreach.refresh_from_db()
        self.assertEqual(outreach.status,"approved")

    def test_due_followup_stays_blocked_without_explicit_enable(self):
        followup=FollowUp.objects.create(lead=self.lead,scheduled_at=timezone.now(),message="Follow up",status="due")
        response=self.client.post(f"/api/followups/{followup.id}/send/",format="json")
        self.assertEqual(response.status_code,400)
        followup.refresh_from_db(); self.assertEqual(followup.status,"due")
