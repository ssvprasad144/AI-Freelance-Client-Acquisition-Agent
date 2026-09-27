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

class AcquisitionPipelineIntegrityTests(TestCase):
    def test_stale_opportunity_stage_cannot_execute_action(self):
        from .models import AcquisitionOpportunity
        from .acquisition_orchestrator import execute_action
        owner=get_user_model().objects.create_user(username="acq-stage-owner",password="pass12345")
        lead=Lead.objects.create(owner=owner,title="Stage test",description="D",source_url="https://example.com/stage",status="new")
        opportunity=AcquisitionOpportunity.objects.create(
            lead=lead,stage="qualified",recommended_action="generate_proposal"
        )
        with self.assertRaisesMessage(ValueError,"Opportunity stage is stale"):
            execute_action(opportunity,"generate_proposal",mode="manual")

    def test_ownerless_opportunity_cannot_execute(self):
        from .models import AcquisitionOpportunity
        from .acquisition_orchestrator import execute_action
        lead=Lead.objects.create(title="Ownerless",description="D",source_url="https://example.com/ownerless",status="new")
        opportunity=AcquisitionOpportunity.objects.create(lead=lead,stage="new",recommended_action="qualify")
        with self.assertRaisesMessage(ValueError,"require an owned lead"):
            execute_action(opportunity,"qualify",mode="manual")

    def test_ensure_opportunity_recalculates_under_lead_lock(self):
        from .models import AcquisitionOpportunity
        from .acquisition_orchestrator import ensure_opportunity
        owner=get_user_model().objects.create_user(username="acq-lock-owner",password="pass12345")
        lead=Lead.objects.create(owner=owner,title="Lock test",description="D",source_url="https://example.com/lock",status="new")
        first=ensure_opportunity(lead)
        lead.status="qualified"
        lead.save(update_fields=["status","updated_at"])
        second=ensure_opportunity(lead)
        self.assertEqual(first.id,second.id)
        self.assertEqual(second.stage,"qualified")
        self.assertEqual(second.recommended_action,"generate_proposal")
