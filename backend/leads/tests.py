from datetime import datetime, timedelta
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from .models import ActivityLog,DiscoveryDomainStat,DiscoveryQueryCache,DiscoverySearchStat,FollowUp,Lead,LeadAnalysis,Outreach,Reply
from .analytics import acquisition_metrics
from .discovery.profiles import query_signature

class APITestBase(TestCase):
    def setUp(self):
        self.client=APIClient(); self.user=get_user_model().objects.create_user(username="testuser",password="testpass123"); self.client.force_authenticate(self.user)
        self.lead=Lead.objects.create(title="Django Automation Engineer",description="Build a Django automation workflow.",source_url="https://example.com/jobs/1")

class AuthTests(TestCase):
    def test_protected_endpoint_requires_auth(self): self.assertEqual(APIClient().get("/api/dashboard/").status_code,401)
    def test_token_endpoint_is_not_exposed(self): self.assertEqual(APIClient().post("/api/auth/token/",{"username":"user","password":"pass12345"},format="json").status_code,404)
    def test_login_returns_token(self):
        get_user_model().objects.create_user(username="user",password="pass12345"); response=APIClient().post("/api/auth/login/",{"username":"user","password":"pass12345"},format="json"); self.assertEqual(response.status_code,200); self.assertTrue(response.data["token"])
    def test_process_due_followups_http_endpoint_is_not_exposed(self): self.assertEqual(APIClient().post("/api/followups/process-due/",format="json").status_code,404)

class FollowUpLifecycleTests(APITestBase):
    def test_create_and_approve_followup(self):
        scheduled=timezone.now()+timedelta(hours=2); response=self.client.post("/api/followups/create/",{"lead_id":self.lead.id,"scheduled_at":scheduled.isoformat(),"message":"Following up on the opportunity."},format="json"); self.assertEqual(response.status_code,200); followup=FollowUp.objects.get(pk=response.data["id"]); self.assertEqual(followup.status,"draft"); response=self.client.post(f"/api/followups/{followup.id}/approve/",format="json"); self.assertEqual(response.status_code,200); followup.refresh_from_db(); self.assertEqual(followup.status,"approved"); self.assertFalse(response.data["sent"])
    def test_due_processing_is_idempotent_and_never_sends(self):
        followup=FollowUp.objects.create(lead=self.lead,scheduled_at=timezone.now()-timedelta(minutes=5),message="Time to follow up.",status="approved"); from .followup_service import process_due_followups
        result=process_due_followups(); self.assertEqual(result["processed"],1); self.assertFalse(result["sent"]); followup.refresh_from_db(); self.assertEqual(followup.status,"due"); self.assertEqual(ActivityLog.objects.filter(event_type="followup.due").count(),1); result=process_due_followups(); self.assertEqual(result["processed"],0)
    def test_future_approved_followup_is_not_due(self):
        FollowUp.objects.create(lead=self.lead,scheduled_at=timezone.now()+timedelta(hours=1),message="Future follow-up.",status="approved"); self.client.post("/api/followups/process-due/",format="json"); response=self.client.get("/api/followups/due/"); self.assertEqual(response.status_code,200); self.assertEqual(response.data["results"],[])
    def test_management_command_processes_due_followup(self): FollowUp.objects.create(lead=self.lead,scheduled_at=timezone.now()-timedelta(minutes=1),message="Worker follow-up.",status="approved"); call_command("process_due_followups"); self.assertEqual(FollowUp.objects.filter(status="due").count(),1); completed=ActivityLog.objects.filter(event_type="cron.followup.completed").latest("created_at"); self.assertTrue(completed.metadata["run_id"]); self.assertGreaterEqual(completed.metadata["duration_ms"],0); self.assertFalse(completed.metadata["sent"])

class LeadLifecycleTests(APITestBase):
    def test_status_and_reply(self):
        response=self.client.post(f"/api/leads/{self.lead.id}/set_status/",{"status":"contacted"},format="json"); self.assertEqual(response.status_code,200); response=self.client.post(f"/api/leads/{self.lead.id}/replies/",{"message":"Thanks, let's discuss.","channel":"email"},format="json"); self.assertEqual(response.status_code,201); self.lead.refresh_from_db(); self.assertEqual(self.lead.status,"replied"); self.assertEqual(Reply.objects.count(),1)

class DiscoveryWorkerTests(APITestBase):
    def _result(self): return {"source":"web_search","model":"gpt-4o-mini","leads":[{"title":"AI Automation Dashboard","company":"Example Client","description":"Build an AI-powered Django automation dashboard.","source":"web_search","source_url":"https://example.com/opportunities/automation","lead_type":"freelance","budget_text":"$1,000","technologies":["Django","AI"],"contact_info":{}}]}
    @patch("leads.discovery_cycle.analyze_lead")
    @patch("leads.discovery_cycle.DiscoveryService.discover")
    def test_discovery_worker_discovers_and_qualifies(self,discover,analyze):
        discover.return_value=self._result(); analyze.return_value={"relevant":True,"match_score":85,"service_match":"AI Products","requirements":["Django"],"pain_points":[],"recommended_approach":"Build the smallest useful workflow first.","matching_projects":["AI Business Automation Dashboard"],"confidence":90,"model":"gpt-4o-mini","input_tokens":10,"output_tokens":10}; call_command("run_discovery_cycle","--source","live","--limit","5"); self.assertEqual(Lead.objects.get(title="AI Automation Dashboard").status,"qualified"); self.assertEqual(DiscoverySearchStat.objects.count(),1); completed=ActivityLog.objects.filter(event_type="cron.discovery.completed").latest("created_at"); self.assertTrue(completed.metadata["run_id"]); self.assertGreaterEqual(completed.metadata["duration_ms"],0)
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


class AdaptiveSearchSelectionTests(TestCase):
    def _stat(self, profile_id, strategy_id, qualified, created=0):
        return DiscoverySearchStat.objects.create(profile_id=profile_id,strategy_id=strategy_id,query=f"{profile_id}-{strategy_id}",normalized_query=f"{profile_id}-{strategy_id}",source="web_search",search_date=timezone.localdate(),qualified=qualified,newly_created_leads=created)

    def test_exploration_covers_under_sampled_arms(self):
        from .discovery.profiles import select_profile
        self._stat("ai-automation","community",5,8)
        selected=select_profile(72,only_if_due=False)
        self.assertNotEqual((selected["id"],selected["strategy_id"]),("ai-automation","community"))

    def test_exploitation_prefers_high_yield_arm_after_exploration(self):
        from .discovery.profiles import select_profile
        profiles=["ai-automation","django-fullstack","interactive-web","startup-build"]
        strategies=["marketplace","community","startup-hiring","direct-web"]
        for pid in profiles:
            for sid in strategies:
                self._stat(pid,sid,1,2)
                self._stat(pid,sid,1,2)
        self._stat("ai-automation","community",8,10)
        selected=select_profile(72,only_if_due=False)
        self.assertEqual((selected["id"],selected["strategy_id"]),("ai-automation","community"))



class WebSearchCostV2Tests(APITestBase):
    def _cached_payload(self):
        return [{"title":"Reusable Django Project","company":"Reuse Client","description":"Build a Django automation project.","source":"web_search","source_url":"https://reuse.example/jobs/1","lead_type":"freelance","technologies":["Django"],"contact_info":{}}]

    @patch("leads.discovery_cycle.DiscoveryService.discover")
    def test_semantic_result_reuse_avoids_second_web_search(self,discover):
        discover.return_value={"source":"web_search","model":"gpt-4o-mini","leads":self._cached_payload()}
        call_command("run_discovery_cycle","--query","current Django freelance opportunities","--source","live")
        call_command("run_discovery_cycle","--query","recent Django freelance project opportunities","--source","live")
        self.assertEqual(discover.call_count,1)

    @patch("leads.discovery_cycle.DiscoveryService.discover")
    def test_dynamic_budget_reduces_searches_when_inventory_is_high(self,discover):
        discover.return_value={"source":"web_search","model":"gpt-4o-mini","leads":[]}
        for i in range(8):
            Lead.objects.create(title=f"Fresh Qualified {i}",description="Django project",source_url=f"https://fresh.example/{i}",status="qualified",last_verified_at=timezone.now())
        with patch("leads.discovery_cycle.settings.DISCOVERY_TARGET_QUALIFIED_LEADS",10), patch("leads.discovery_cycle.settings.DISCOVERY_MAX_SEARCHES_PER_DAY",4):
            ActivityLog.objects.create(event_type="discovery.search",message="prior",metadata={})
            ActivityLog.objects.create(event_type="discovery.search",message="prior",metadata={})
            result=__import__("leads.discovery_cycle",fromlist=["run_discovery_cycle"]).run_discovery_cycle(query="Django freelance",profile_id="budget-test")
        self.assertEqual(discover.call_count,0)
        self.assertIn(result["skip_reason"],{"dynamic daily web-search budget exhausted","fresh qualified lead inventory is already healthy"})

    @patch("leads.discovery_cycle.DiscoveryService.discover")
    def test_cross_profile_cache_reuse(self,discover):
        payload=self._cached_payload()
        DiscoveryQueryCache.objects.create(profile_id="ai-automation",normalized_query="current django automation client request",query="current django automation client request",query_family="ai-automation:community",query_signature=query_signature("current django automation client request"),searched_at=timezone.now(),result_count=1,result_payload=payload,source_domains=["reuse.example"])
        result=__import__("leads.discovery_cycle",fromlist=["run_discovery_cycle"]).run_discovery_cycle(query="current django automation project request",profile_id="django-fullstack",strategy_id="community")
        self.assertEqual(discover.call_count,0)
        self.assertTrue(result["reused"])

    def test_domain_learning_records_source_domains(self):
        DiscoveryDomainStat.objects.create(domain="example.com",searches=3,results=20,qualified=1)
        from .discovery.profiles import domain_performance
        self.assertEqual(domain_performance()[0]["domain"],"example.com")

    def test_query_variants_are_tracked(self):
        DiscoverySearchStat.objects.create(profile_id="ai-automation",strategy_id="community",query="x",normalized_query="x",query_family="ai-automation:community",query_variant="client-request",source="web_search",search_date=timezone.localdate(),qualified=2)
        from .discovery.profiles import select_query_variant
        self.assertIn(select_query_variant("ai-automation","community"),{"base","recent","client-request","project"})

    def test_adaptive_context_stays_low_for_new_arms(self):
        from .discovery.profiles import select_context_size
        self.assertEqual(select_context_size("ai-automation","community"),"low")

    def test_preferred_search_window_can_defer_search(self):
        from .discovery.profiles import preferred_search_window_open
        with patch("leads.discovery.profiles.settings.DISCOVERY_PREFERRED_HOURS_ENABLED",True), patch("leads.discovery.profiles.timezone.localtime",return_value=datetime(2026,1,1,3,0,tzinfo=timezone.get_current_timezone())):
            self.assertFalse(preferred_search_window_open())
