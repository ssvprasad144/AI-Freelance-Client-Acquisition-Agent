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
