from datetime import datetime, timedelta
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from .models import ActivityLog,DiscoveryDomainStat,DiscoveryQueryCache,DiscoverySearchStat,FollowUp,Lead,LeadAnalysis,Outreach,Reply,LearningStat


class SerializerLifecycleFieldHardeningTests(TestCase):
    def test_lead_serializer_rejects_owner_and_status_tampering(self):
        owner=get_user_model().objects.create_user(username="serializer-owner",password="pass12345")
        other=get_user_model().objects.create_user(username="serializer-other",password="pass12345")
        lead=Lead.objects.create(owner=owner,title="Protected lead",description="Test",source_url="https://example.com/protected")
        client=APIClient()
        client.force_authenticate(owner)
        response=client.patch(
            f"/api/leads/{lead.id}/",
            {"owner":other.id,"status":"won","title":"Updated title"},
            format="json",
        )
        self.assertEqual(response.status_code,200)
        lead.refresh_from_db()
        self.assertEqual(lead.owner_id,owner.id)
        self.assertEqual(lead.status,"new")
        self.assertEqual(lead.title,"Updated title")


class LearningOwnerIsolationTests(TestCase):
    def test_learning_refresh_and_api_are_owner_scoped(self):
        owner=get_user_model().objects.create_user(username="learning-owner-a",password="pass12345")
        other=get_user_model().objects.create_user(username="learning-owner-b",password="pass12345")
        Lead.objects.create(owner=owner,title="Owner lead",description="Django",source_url="https://example.com/a",source="owner-source")
        Lead.objects.create(owner=other,title="Other lead",description="Django",source_url="https://example.com/b",source="other-source")
        from .learning import refresh_learning
        owner_stats=refresh_learning(owner=owner)
        self.assertTrue(owner_stats)
        self.assertTrue(all(row["owner_id"]==owner.id for row in owner_stats))
        self.assertFalse(LearningStat.objects.filter(owner=other).exists())
        from rest_framework.test import APIClient
        client=APIClient()
        client.force_authenticate(owner)
        response=client.get("/api/learning/")
        self.assertEqual(response.status_code,200)
        self.assertTrue(all(row["owner"]==owner.id for row in response.data["stats"]))


class LeadCreationOwnershipTests(TestCase):
    def test_authenticated_api_lead_creation_assigns_owner(self):
        owner=get_user_model().objects.create_user(username="creation-owner",password="pass12345")
        client=APIClient()
        client.force_authenticate(owner)
        response=client.post(
            "/api/leads/",
            {
                "title":"API-created lead",
                "description":"A Django automation opportunity.",
                "source_url":"https://example.com/opportunity",
                "company":"Example Co",
            },
            format="json",
        )
        self.assertEqual(response.status_code,201)
        lead=Lead.objects.get(pk=response.data["id"])
        self.assertEqual(lead.owner_id,owner.id)

    def test_authenticated_api_cannot_create_ownerless_lead(self):
        owner=get_user_model().objects.create_user(username="creation-owner-2",password="pass12345")
        client=APIClient()
        client.force_authenticate(owner)
        response=client.post(
            "/api/leads/",
            {
                "title":"Owner protection",
                "description":"Protected creation.",
                "source_url":"https://example.com/protected",
                "owner":None,
            },
            format="json",
        )
        self.assertEqual(response.status_code,201)
        self.assertEqual(Lead.objects.get(pk=response.data["id"]).owner_id,owner.id)

class DataIntegrityAuditTests(TestCase):
    def test_optimization_report_is_owner_scoped(self):
        from .models import RevenueRecord
        from .revenue_intelligence import optimization_report, refresh_revenue_learning
        owner=get_user_model().objects.create_user(username="integrity-owner",password="pass12345")
        other=get_user_model().objects.create_user(username="integrity-other",password="pass12345")
        lead_a=Lead.objects.create(owner=owner,title="Owner opportunity",description="A",source_url="https://example.com/a",status="won",source="owner")
        lead_b=Lead.objects.create(owner=other,title="Other opportunity",description="B",source_url="https://example.com/b",status="won",source="other")
        RevenueRecord.objects.create(lead=lead_a,won_value=100,source="owner")
        RevenueRecord.objects.create(lead=lead_b,won_value=900,source="other")
        LearningStat.objects.create(owner=owner,dimension="source",key="owner",attempts=2)
        LearningStat.objects.create(owner=other,dimension="source",key="other",attempts=2)
        refresh_revenue_learning(owner=owner)
        report=optimization_report(owner=owner)
        self.assertEqual(len(report),1)
        self.assertEqual(report[0]["key"],"owner")
        self.assertEqual(report[0]["reward"],100)

    def test_workspace_detects_cross_owner_relationships(self):
        from .models import Client, Contact
        from .lifecycle_service import validate_workspace
        owner=get_user_model().objects.create_user(username="workspace-owner",password="pass12345")
        other=get_user_model().objects.create_user(username="workspace-other",password="pass12345")
        client=Client.objects.create(owner=owner,company="Owner Co",normalized_company="owner co")
        other_lead=Lead.objects.create(owner=other,title="Cross owner",description="X",source_url="https://example.com/x",client=client)
        contact=Contact.objects.create(client=client,name="Contact")
        other_lead.contact=contact
        other_lead.save(update_fields=["contact","updated_at"])
        report=validate_workspace(owner)
        codes={row["code"] for row in report["violations"]}
        self.assertIn("client_has_cross_owner_lead",codes)

        other_client=Client.objects.create(owner=other,company="Other Co",normalized_company="other co")
        wrong_contact=Contact.objects.create(client=other_client,name="Wrong Contact")
        Lead.objects.create(owner=owner,title="Wrong contact",description="Y",source_url="https://example.com/y",client=client,contact=wrong_contact)
        refreshed_codes={row["code"] for row in validate_workspace(owner)["violations"]}
        self.assertIn("contact_client_mismatch",refreshed_codes)

    def test_pipeline_detects_contact_without_client(self):
        from .models import Contact, Client
        from .lifecycle_service import validate_pipeline_invariants
        owner=get_user_model().objects.create_user(username="pipeline-owner",password="pass12345")
        client=Client.objects.create(owner=owner,company="Client",normalized_company="client")
        contact=Contact.objects.create(client=client,name="Contact")
        lead=Lead.objects.create(owner=owner,title="Bad relation",description="X",source_url="https://example.com/x",contact=contact)
        self.assertIn("contact_without_client",validate_pipeline_invariants(lead))

class OutboundAmbiguousDeliveryTests(TestCase):
    def test_stale_sending_claims_are_not_automatically_retried(self):
        from django.utils import timezone
        from datetime import timedelta
        from .models import Outreach, FollowUp
        owner=get_user_model().objects.create_user(username="outbound-owner",password="pass12345")
        lead=Lead.objects.create(owner=owner,title="Outbound safety lead",description="Test",source_url="https://example.com/outbound",contact_info={"email":"client@example.com"})
        old=timezone.now()-timedelta(minutes=45)
        outreach=Outreach.objects.create(lead=lead,channel="email",medium="email",message="Test outreach",status="sending")
        Outreach.objects.filter(pk=outreach.pk).update(updated_at=old)
        followup=FollowUp.objects.create(lead=lead,scheduled_at=timezone.now(),message="Test follow-up",status="sending")
        FollowUp.objects.filter(pk=followup.pk).update(updated_at=old)
        from .followup_service import recover_stale_outbound_claims
        result=recover_stale_outbound_claims(max_age_minutes=30)
        outreach.refresh_from_db(); followup.refresh_from_db()
        self.assertEqual(outreach.status,"send_uncertain")
        self.assertEqual(followup.status,"send_uncertain")
        self.assertEqual(result["outreach"],1)
        self.assertEqual(result["followups"],1)

    def test_ambiguous_delivery_cannot_be_sent_again(self):
        from .models import Outreach, FollowUp
        from .acquisition import send_email, send_followup
        owner=get_user_model().objects.create_user(username="outbound-block",password="pass12345")
        lead=Lead.objects.create(owner=owner,title="Ambiguous lead",description="Test",source_url="https://example.com/ambiguous",contact_info={"email":"client@example.com"})
        outreach=Outreach.objects.create(lead=lead,channel="email",medium="email",message="Test",status="send_uncertain")
        followup=FollowUp.objects.create(lead=lead,scheduled_at=timezone.now(),message="Test",status="send_uncertain")
        with self.assertRaises(ValueError): send_email(outreach)
        with self.assertRaises(ValueError): send_followup(followup)
class DatabaseIntegrityAuditTests(TestCase):
    def test_learning_stat_uniqueness_is_scoped_to_owner(self):
        owner=get_user_model().objects.create_user(username="learning-db-owner-a",password="pass12345")
        other=get_user_model().objects.create_user(username="learning-db-owner-b",password="pass12345")
        LearningStat.objects.create(owner=owner,dimension="source",key="shared-key",attempts=2)
        LearningStat.objects.create(owner=other,dimension="source",key="shared-key",attempts=3)
        self.assertEqual(LearningStat.objects.filter(dimension="source",key="shared-key").count(),2)

    def test_learning_stat_duplicate_for_same_owner_is_rejected(self):
        from django.db import IntegrityError
        owner=get_user_model().objects.create_user(username="learning-db-owner-c",password="pass12345")
        LearningStat.objects.create(owner=owner,dimension="source",key="same-key",attempts=1)
        with self.assertRaises(IntegrityError):
            LearningStat.objects.create(owner=owner,dimension="source",key="same-key",attempts=2)

class DiscoveryIntegrityTests(TestCase):
    def test_duplicate_normalized_source_url_is_blocked_per_owner(self):
        from django.db import IntegrityError

        owner=get_user_model().objects.create_user(username="discovery-owner",password="pass12345")
        Lead.objects.create(
            owner=owner,
            title="First opportunity",
            normalized_title="first opportunity",
            normalized_url="example.com/opportunity/1",
            company="Example Co",
            description="First",
            source_url="https://example.com/opportunity/1",
        )
        with self.assertRaises(IntegrityError):
            Lead.objects.create(
                owner=owner,
                title="Duplicate opportunity",
                normalized_title="duplicate opportunity",
                normalized_url="example.com/opportunity/1",
                company="Example Co",
                description="Duplicate",
                source_url="https://example.com/opportunity/1",
            )

    def test_same_normalized_source_url_is_allowed_for_different_owners(self):
        owner=get_user_model().objects.create_user(username="discovery-owner-a",password="pass12345")
        other=get_user_model().objects.create_user(username="discovery-owner-b",password="pass12345")
        for user,title in ((owner,"Owner A lead"),(other,"Owner B lead")):
            Lead.objects.create(
                owner=user,
                title=title,
                normalized_title=title.lower(),
                normalized_url="example.com/shared/1",
                company="Example Co",
                description="Shared public opportunity",
                source_url="https://example.com/shared/1",
            )
        self.assertEqual(Lead.objects.filter(normalized_url="example.com/shared/1").count(),2)


class SourceBoundEvidenceIntegrityTests(TestCase):
    def test_evidence_requires_excerpt_from_the_claimed_source_url(self):
        from .data_quality import source_supported_evidence
        findings=[
            {"url":"https://source-a.example/job/1","excerpt":"Senior Django developer needed for Example A."},
            {"url":"https://source-b.example/job/2","excerpt":"Senior Django developer needed for Example B."},
        ]
        self.assertTrue(source_supported_evidence("Senior Django developer", "https://source-a.example/job/1", findings))
        self.assertFalse(source_supported_evidence("Senior Django developer needed for Example B.", "https://source-a.example/job/1", findings))

    def test_created_lead_persists_url_bound_evidence(self):
        from .discovery_cycle import _store
        from .models import LeadEvidence
        owner=get_user_model().objects.create_user(username="evidence-owner",password="pass12345")
        item={
            "title":"Django developer",
            "company":"Example",
            "description":"Senior Django developer needed for Example.",
            "source":"web_search",
            "source_url":"https://example.com/jobs/1",
            "action_url":"https://example.com/jobs/1/apply",
            "lead_type":"freelance",
            "budget_text":"",
            "technologies":["Django"],
            "contact_info":{},
        }
        created,duplicates,invalid=_store(
            [item],
            owner=owner,
            source_findings=[
                {"url":"https://example.com/jobs/1","excerpt":"Django developer Senior Django developer needed for Example."},
            ],
        )
        self.assertEqual((created,duplicates,invalid),(1,0,0))
        evidence=LeadEvidence.objects.filter(lead__owner=owner)
        self.assertTrue(evidence.filter(field_name="description",source_supported=True,validation_status="validated").exists())
        self.assertFalse(evidence.filter(field_name="action_url",source_supported=True).exists())


class AIQualificationLifecycleTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user(username="ai-lifecycle-owner",password="pass12345")

    def test_invalid_boolean_match_score_is_rejected(self):
        from .ai_service import _validated_analysis
        payload={"relevant":True,"match_score":True,"service_match":"Django","requirements":[],"pain_points":[],"recommended_approach":"Review scope.","matching_projects":[],"confidence":80}
        with self.assertRaises(ValueError):
            _validated_analysis(payload)

    @patch("leads.ai_service.OpenAI")
    @patch("leads.ai_service.settings.OPENAI_API_KEY","test-key")
    def test_provider_failure_uses_deterministic_fallback(self, openai_cls):
        openai_cls.return_value.responses.create.side_effect=RuntimeError("provider unavailable")
        from .ai_service import analyze_lead
        lead=Lead.objects.create(owner=self.user,title="Build Django API",description="Need a Django API for an automation platform.",source_url="https://example.com/job")
        result=analyze_lead(lead)
        self.assertEqual(result["model"],"deterministic-fallback")
        self.assertTrue(ActivityLog.objects.filter(lead=lead,event_type="ai.provider_error").exists())

    def test_lead_content_update_invalidates_existing_analysis(self):
        lead=Lead.objects.create(owner=self.user,title="Build Django API",description="Need a Django API.",source_url="https://example.com/job")
        LeadAnalysis.objects.create(lead=lead,input_fingerprint="stale",relevant=True,match_score=90)
        client=APIClient()
        client.force_authenticate(self.user)
        response=client.patch(f"/api/leads/{lead.id}/",{"description":"Need a React dashboard instead."},format="json")
        self.assertEqual(response.status_code,200)
        self.assertFalse(LeadAnalysis.objects.filter(lead=lead).exists())


class APILifecycleAuditTests(TestCase):
    def setUp(self):
        self.owner=get_user_model().objects.create_user(username="api-audit-owner",password="pass12345")
        self.other=get_user_model().objects.create_user(username="api-audit-other",password="pass12345")
        self.client=APIClient()
        self.client.force_authenticate(self.owner)

    def test_acquisition_action_rejects_string_false_as_approval(self):
        lead=Lead.objects.create(owner=self.owner,title="Qualified lead",description="Django project",source_url="https://example.com/qualified",status="qualified")
        LeadAnalysis.objects.create(lead=lead,relevant=True,match_score=90,service_match="Django",confidence=90,input_fingerprint="")
        from .acquisition_orchestrator import ensure_opportunity
        opportunity=ensure_opportunity(lead)
        response=self.client.post(
            f"/api/acquisition/{opportunity.id}/action/",
            {"action":"generate_proposal","mode":"approval_required","approved":"false"},
            format="json",
        )
        self.assertEqual(response.status_code,200)
        self.assertFalse(response.data["executed"])
        self.assertTrue(response.data["requires_approval"])
        self.assertEqual(lead.outreach.count(),0)

    def test_acquisition_action_rejects_invalid_boolean(self):
        lead=Lead.objects.create(owner=self.owner,title="Qualified lead",description="Django project",source_url="https://example.com/qualified-2",status="qualified")
        LeadAnalysis.objects.create(lead=lead,relevant=True,match_score=90,service_match="Django",confidence=90,input_fingerprint="")
        from .acquisition_orchestrator import ensure_opportunity
        opportunity=ensure_opportunity(lead)
        response=self.client.post(
            f"/api/acquisition/{opportunity.id}/action/",
            {"action":"generate_proposal","mode":"approval_required","approved":"maybe"},
            format="json",
        )
        self.assertEqual(response.status_code,400)
        self.assertFalse(response.data["executed"])

    def test_invalid_meeting_transition_returns_400(self):
        from .models import Client, Meeting
        client=Client.objects.create(owner=self.owner,company="Meeting Client",normalized_company="meeting client")
        meeting=Meeting.objects.create(client=client,status="completed")
        response=self.client.patch(
            f"/api/meetings/{meeting.id}/",
            {"status":"scheduled"},
            format="json",
        )
        self.assertEqual(response.status_code,400)
        meeting.refresh_from_db()
        self.assertEqual(meeting.status,"completed")

    def test_cross_owner_meeting_is_not_mutable(self):
        from .models import Meeting
        lead=Lead.objects.create(owner=self.other,title="Other lead",description="Other",source_url="https://example.com/other-meeting")
        meeting=Meeting.objects.create(lead=lead,status="requested")
        response=self.client.patch(
            f"/api/meetings/{meeting.id}/",
            {"status":"cancelled"},
            format="json",
        )
        self.assertEqual(response.status_code,404)
        meeting.refresh_from_db()
        self.assertEqual(meeting.status,"requested")

    def test_invalid_numeric_limit_returns_400(self):
        response=self.client.post("/api/leads/discovery/qualify/",{"limit":"not-a-number"},format="json")
        self.assertEqual(response.status_code,400)
        self.assertIn("limit",response.data["detail"])
