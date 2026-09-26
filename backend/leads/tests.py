from datetime import timedelta

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import ActivityLog, FollowUp, Lead


class FollowUpLifecycleTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.lead = Lead.objects.create(
            title="Django Automation Engineer",
            description="Build a Django automation workflow.",
            source_url="https://example.com/jobs/1",
        )

    def test_create_and_approve_followup(self):
        scheduled = timezone.now() + timedelta(hours=2)
        response = self.client.post(
            "/api/followups/create/",
            {"lead_id": self.lead.id, "scheduled_at": scheduled.isoformat(), "message": "Following up on the opportunity."},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        followup = FollowUp.objects.get(pk=response.data["id"])
        self.assertEqual(followup.status, "draft")

        response = self.client.post(f"/api/followups/{followup.id}/approve/", format="json")
        self.assertEqual(response.status_code, 200)
        followup.refresh_from_db()
        self.assertEqual(followup.status, "approved")
        self.assertFalse(response.data["sent"])

    def test_due_processing_is_idempotent_and_never_sends(self):
        followup = FollowUp.objects.create(
            lead=self.lead,
            scheduled_at=timezone.now() - timedelta(minutes=5),
            message="Time to follow up.",
            status="approved",
        )

        response = self.client.post("/api/followups/process-due/", format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["processed"], 1)
        self.assertFalse(response.data["sent"])

        followup.refresh_from_db()
        self.assertEqual(followup.status, "due")
        self.assertEqual(ActivityLog.objects.filter(event_type="followup.due").count(), 1)

        response = self.client.post("/api/followups/process-due/", format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["processed"], 0)
        self.assertEqual(ActivityLog.objects.filter(event_type="followup.due").count(), 1)

    def test_future_approved_followup_is_not_due(self):
        FollowUp.objects.create(
            lead=self.lead,
            scheduled_at=timezone.now() + timedelta(hours=1),
            message="Future follow-up.",
            status="approved",
        )

        response = self.client.post("/api/followups/process-due/", format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["processed"], 0)

        response = self.client.get("/api/followups/due/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])


    def test_management_command_processes_due_followup(self):
        FollowUp.objects.create(
            lead=self.lead,
            scheduled_at=timezone.now() - timedelta(minutes=1),
            message="Worker follow-up.",
            status="approved",
        )

        call_command("process_due_followups")

        self.assertEqual(
            FollowUp.objects.filter(status="due").count(),
            1,
        )
