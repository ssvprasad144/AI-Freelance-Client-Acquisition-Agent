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
