from datetime import timedelta
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient
from .models import Lead, Meeting, Client, LearningStat
from .client_service import sync_lead_client, record_message
from .learning import refresh_learning

class Phase1115Tests(TestCase):
    def setUp(self):
        self.client=APIClient()
        user=get_user_model().objects.create_user(username="phase1115",password="pass1234")
        self.client.force_authenticate(user)
        self.lead=Lead.objects.create(
            title="AI automation dashboard",description="Build a Django React AI automation dashboard.",
            company="Acme Labs",source="linkedin",source_url="https://linkedin.com/jobs/view/1",
            action_url="https://linkedin.com/jobs/view/1",contact_info={"email":"client@example.com","name":"Client","profile_url":"https://linkedin.com/in/client"}
        )

    def test_client_memory_deduplicates_company(self):
        client1,contact1=sync_lead_client(self.lead)
        second=Lead.objects.create(title="Second opportunity",description="Django work",company="ACME LABS",source="reddit",source_url="https://reddit.com/r/test/1",contact_info={"email":"other@example.com"})
        client2,contact2=sync_lead_client(second)
        self.assertEqual(client1.id,client2.id)
        self.assertEqual(Client.objects.count(),1)

    def test_conversation_records_direction(self):
        client,contact=sync_lead_client(self.lead)
        record_message(client,self.lead,"linkedin","outbound","Hello",contact=contact)
        record_message(client,self.lead,"linkedin","inbound","Interested",contact=contact)
        self.assertEqual(client.conversations.first().messages.count(),2)

    def test_meeting_api_and_learning(self):
        client,contact=sync_lead_client(self.lead)
        response=self.client.post("/api/meetings/create/",{"lead_id":self.lead.id,"status":"scheduled","scheduled_at":(timezone.now()+timedelta(days=1)).isoformat(),"meeting_url":"https://meet.example.com/1"},format="json")
        self.assertEqual(response.status_code,201)
        self.lead.status="won"; self.lead.save(update_fields=["status","updated_at"])
        stats=refresh_learning()
        self.assertTrue(LearningStat.objects.filter(dimension="source",key="linkedin",wins=1).exists())
        self.assertTrue(Meeting.objects.filter(client=client,status="scheduled").exists())
