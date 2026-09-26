from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from .models import Lead, OutreachPlan
from .outreach_intelligence import create_plan, eligible, mark_approved

class Phase17Tests(TestCase):
    """Regression coverage for safe, context-aware multichannel outreach (CI)."""
    def setUp(self):
        self.api=APIClient(); user=get_user_model().objects.create_user(username="p17",password="pass123"); self.api.force_authenticate(user)
        self.lead=Lead.objects.create(title="Django automation",description="Build automation",status="qualified",action_url="https://example.com/apply",contact_info={"email":"a@example.com","name":"Alex"})
    def test_personalized_plan_and_channel_safety(self):
        plan=create_plan(self.lead,"email","A")
        self.assertTrue(plan.automatic); self.assertIn("Alex",plan.message)
        self.assertEqual(self.api.get("/api/outreach/strategy/").status_code,200)
    def test_reply_stops_outreach(self):
        self.lead.status="replied"; self.lead.save(update_fields=["status","updated_at"])
        self.assertFalse(eligible(self.lead))
    def test_approval_creates_safe_outreach_handoff(self):
        plan=create_plan(self.lead,"email","A")
        mark_approved(plan)
        self.assertTrue(self.lead.outreach.filter(status="approved",medium="email").exists())

    def test_manual_channel_never_marked_automatic(self):
        plan=create_plan(self.lead,"linkedin","B")
        self.assertFalse(plan.automatic)
        self.assertEqual(plan.destination_url,"https://example.com/apply")
