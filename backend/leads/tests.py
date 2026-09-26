from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from .models import ActivityLog,DiscoveryQueryCache,DiscoverySearchStat,FollowUp,Lead,LeadAnalysis,Outreach,Reply
from .analytics import acquisition_metrics

class APITestBase(TestCase):
    def setUp(self):
        self.client=APIClient(); self.user=get_user_model().objects.create_user(username="testuser",password="testpass123"); self.client.force_authenticate(self.user)
        self.lead=Lead.objects.create(title="Django Automation Engineer",description="Build a Django automation workflow.",source_url="https://example.com/jobs/1")

class AuthTests(TestCase):
    def test_protected_endpoint_requires_auth(self): self.assertEqual(APIClient().get("/api/dashboard/").status_code,401)
    def test_login_returns_token(self):
        get_user_model().objects.create_user(username="user",password="pass12345"); response=APIClient().post("/api/auth/login/",{"username":"user","password":"pass12345"},format="json"); self.assertEqual(response.status_code,200); self.assertTrue(response.data["token"])

class FollowUpLifecycleTests(APITestBase):
    def test_create_and_approve_followup(self):
        scheduled=timezone.now()+timedelta(hours=2); response=self.client.post("/api/followups/create/",{"lead_id":self.lead.id,"scheduled_at":scheduled.isoformat(),"message":"Following up on the opportunity."},format="json"); self.assertEqual(response.status_code,200); followup=FollowUp.objects.get(pk=response.data["id"]); self.assertEqual(followup.status,"draft"); response=self.client.post(f"/api/followups/{followup.id}/approve/",format="json"); self.assertEqual(response.status_code,200); followup.refresh_from_db(); self.assertEqual(followup.status,"approved"); self.assertFalse(response.data["sent"])
    def test_due_processing_is_idempotent_and_never_sends(self):
        followup=FollowUp.objects.create(lead=self.lead,scheduled_at=timezone.now()-timedelta(minutes=5),message="Time to follow up.",status="approved"); response=self.client.post("/api/followups/process-due/",format="json"); self.assertEqual(response.status_code,200); self.assertEqual(response.data["processed"],1); self.assertFalse(response.data["sent"]); followup.refresh_from_db(); self.assertEqual(followup.status,"due"); self.assertEqual(ActivityLog.objects.filter(event_type="followup.due").count(),1); response=self.client.post("/api/followups/process-due/",format="json"); self.assertEqual(response.data["processed"],0)
    def test_future_approved_followup_is_not_due(self):
        FollowUp.objects.create(lead=self.lead,scheduled_at=timezone.now()+timedelta(hours=1),message="Future follow-up.",status="approved"); self.client.post("/api/followups/process-due/",format="json"); response=self.client.get("/api/followups/due/"); self.assertEqual(response.status_code,200); self.assertEqual(response.data["results"],[])
    def test_management_command_processes_due_followup(self): FollowUp.objects.create(lead=self.lead,scheduled_at=timezone.now()-timedelta(minutes=1),message="Worker follow-up.",status="approved"); call_command("process_due_followups"); self.assertEqual(FollowUp.objects.filter(status="due").count(),1)

class LeadLifecycleTests(APITestBase):
    def test_status_and_reply(self):
        response=self.client.post(f"/api/leads/{self.lead.id}/set_status/",{"status":"contacted"},format="json"); self.assertEqual(response.status_code,200); response=self.client.post(f"/api/leads/{self.lead.id}/replies/",{"message":"Thanks, let's discuss.","channel":"email"},format="json"); self.assertEqual(response.status_code,201); self.lead.refresh_from_db(); self.assertEqual(self.lead.status,"replied"); self.assertEqual(Reply.objects.count(),1)

class DiscoveryWorkerTests(APITestBase):
    def _result(self): return {"source":"web_search","model":"gpt-4o-mini","leads":[{"title":"AI Automation Dashboard","company":"Example Client","description":"Build an AI-powered Django automation dashboard.","source":"web_search","source_url":"https://example.com/opportunities/automation","lead_type":"freelance","budget_text":"$1,000","technologies":["Django","AI"],"contact_info":{}}]}
    @patch("leads.discovery_cycle.analyze_lead")
    @patch("leads.discovery_cycle.DiscoveryService.discover")
    def test_discovery_worker_discovers_and_qualifies(self,discover,analyze):
        discover.return_value=self._result(); analyze.return_value={"relevant":True,"match_score":85,"service_match":"AI Products","requirements":["Django"],"pain_points":[],"recommended_approach":"Build the smallest useful workflow first.","matching_projects":["AI Business Automation Dashboard"],"confidence":90,"model":"gpt-4o-mini","input_tokens":10,"output_tokens":10}; call_command("run_discovery_cycle","--source","live","--limit","5"); self.assertEqual(Lead.objects.get(title="AI Automation Dashboard").status,"qualified"); self.assertEqual(DiscoverySearchStat.objects.count(),1)
    @patch("leads.discovery_cycle.analyze_lead")
    @patch("leads.discovery_cycle.DiscoveryService.discover")
    def test_discovery_worker_deduplicates_on_repeat_cycle(self,discover,analyze):
        discover.return_value=self._result(); analyze.return_value={"relevant":False,"match_score":20,"service_match":"Needs review","requirements":[],"pain_points":[],"recommended_approach":"Review manually.","matching_projects":[],"confidence":30,"model":"gpt-4o-mini","input_tokens":10,"output_tokens":10}; call_command("run_discovery_cycle","--limit","5"); call_command("run_discovery_cycle","--limit","5"); self.assertEqual(Lead.objects.filter(title="AI Automation Dashboard").count(),1)

class AcquisitionEngineTests(APITestBase):
    def test_discovery_profiles_are_available(self): response=self.client.get("/api/discovery/profiles/"); self.assertEqual(response.status_code,200); self.assertGreaterEqual(len(response.data["profiles"]),4)

class PublicCrawlerSafetyTests(TestCase):
    def test_private_hosts_are_blocked(self):
        from .discovery.public_crawler import CrawlError,_validate_url
        for url in ["http://127.0.0.1/admin","http://10.0.0.1/internal","http://localhost:8000/"]:
            with self.assertRaises(CrawlError): _validate_url(url)
    def test_credential_urls_are_blocked(self):
        from .discovery.public_crawler import CrawlError,_validate_url
        with self.assertRaises(CrawlError): _validate_url("https://user:password@example.com/jobs")
    @patch("leads.discovery.live_provider.OpenAI")
    def test_live_discovery_returns_search_results_without_crawling(self,client):
        response=client.return_value.responses.create.return_value; response.output_text='{"leads":[{"title":"Django role","company":"Example","description":"Build Django app","source":"web_search","source_url":"https://example.com/jobs/1","lead_type":"freelance","budget_text":"","technologies":["Django"],"contact_info":{}}]}'; from .discovery.live_provider import discover_live
        with patch("leads.discovery.live_provider.settings.OPENAI_API_KEY","test-key"),patch("leads.discovery.live_provider.settings.DISCOVERY_MODEL","gpt-4o-mini"),patch("leads.discovery.live_provider.settings.DISCOVERY_SEARCH_CONTEXT_SIZE","medium"),patch("leads.discovery.live_provider.settings.DISCOVERY_MAX_RESULTS",5): result=discover_live("Django freelance")
        self.assertEqual(len(result["leads"]),1)

class DiscoveryOptimizationTests(APITestBase):
    @patch("leads.discovery_cycle.DiscoveryService.discover")
    def test_recent_query_is_served_from_cache(self,discover):
        discover.return_value={"source":"web_search","model":"gpt-4o-mini","leads":[]}; call_command("run_discovery_cycle","--query","AI automation freelance"); call_command("run_discovery_cycle","--query","AI automation freelance"); self.assertEqual(discover.call_count,1); self.assertTrue(ActivityLog.objects.filter(event_type="discovery.cache_hit").exists())
    @patch("leads.discovery_cycle.DiscoveryService.discover")
    def test_worker_rotates_across_profiles(self,discover):
        discover.return_value={"source":"web_search","model":"gpt-4o-mini","leads":[]}; call_command("run_discovery_cycle"); call_command("run_discovery_cycle"); self.assertEqual(discover.call_count,2); self.assertEqual(DiscoveryQueryCache.objects.count(),2)
    def test_proposal_requires_qualified_analysis(self):
        self.lead.status="new"; self.lead.save(update_fields=["status"]); LeadAnalysis.objects.create(lead=self.lead,relevant=True,match_score=40,model="gpt-4o-mini"); response=self.client.post(f"/api/leads/{self.lead.id}/proposal/",format="json"); self.assertEqual(response.status_code,400)

class LeadOptimizationTests(TestCase):
    def test_local_prefilter_accepts_relevant_lead(self):
        from .lead_optimizer import local_lead_score,should_ai_qualify
        lead=Lead(title="Build Django AI automation dashboard",description="Need a Python Django developer to build an AI workflow.",source_url="https://example.com/jobs/1",technologies=["Django","AI"]); result=local_lead_score(lead); self.assertTrue(result["service_hits"]); self.assertTrue(should_ai_qualify(lead))
    def test_local_prefilter_rejects_obvious_mismatch(self):
        from .lead_optimizer import local_lead_score,should_ai_qualify
        lead=Lead(title="SEO content writer",description="Need blog posts and SEO content writing.",source_url="https://example.com/jobs/2",technologies=["SEO"]); result=local_lead_score(lead); self.assertFalse(result["service_hits"]); self.assertFalse(should_ai_qualify(lead))
    @patch("leads.discovery_cycle.analyze_lead")
    @patch("leads.discovery_cycle.DiscoveryService.discover")
    def test_irrelevant_lead_is_filtered_without_ai_call(self,discover,analyze):
        discover.return_value={"source":"web_search","model":"gpt-4o-mini","leads":[{"title":"SEO content writer","company":"Example","description":"Need SEO content writing.","source":"web_search","source_url":"https://example.com/jobs/3","lead_type":"freelance","budget_text":"","technologies":["SEO"],"contact_info":{}}]}; call_command("run_discovery_cycle","--limit","5"); self.assertEqual(analyze.call_count,0)

class SearchBudgetOptimizationTests(APITestBase):
    @patch("leads.discovery_cycle.DiscoveryService.discover")
    def test_daily_search_budget_skips_live_search(self,discover):
        discover.return_value={"source":"web_search","model":"gpt-4o-mini","leads":[]};
        with patch("leads.discovery_cycle.settings.DISCOVERY_MAX_SEARCHES_PER_DAY",1):
            ActivityLog.objects.create(event_type="discovery.search",message="prior search",metadata={}); result=__import__("leads.discovery_cycle",fromlist=["run_discovery_cycle"]).run_discovery_cycle(query="Django freelance",profile_id="test")
        self.assertEqual(discover.call_count,0); self.assertFalse(result["searched"])
    @patch("leads.discovery_cycle.DiscoveryService.discover")
    def test_healthy_inventory_skips_live_search(self,discover):
        from leads.discovery_cycle import run_discovery_cycle
        for i in range(10): Lead.objects.create(title=f"Qualified {i}",description="Django project",source_url=f"https://example.com/{i}",status="qualified")
        with patch("leads.discovery_cycle.settings.DISCOVERY_TARGET_QUALIFIED_LEADS",10): result=run_discovery_cycle(query="Django freelance",profile_id="inventory-test")
        self.assertEqual(discover.call_count,0); self.assertFalse(result["searched"])

class SearchLearningTests(APITestBase):
    def test_analytics_exposes_search_learning(self):
        DiscoverySearchStat.objects.create(profile_id="django-fullstack",query="django freelance",normalized_query="django freelance",source="web_search",search_date=timezone.localdate(),raw_results=12,qualified=3)
        metrics=acquisition_metrics(); row=metrics["search_learning"][0]; self.assertEqual(row["searches"],1); self.assertEqual(row["qualified_per_search"],3.0)
