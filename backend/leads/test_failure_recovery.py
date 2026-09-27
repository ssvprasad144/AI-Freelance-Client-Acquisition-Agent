from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from .followup_service import recover_stale_outbound_claims
from .models import FollowUp, Outreach, Lead


class FailureRecoveryTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="recovery-owner", password="pass12345")
        self.lead = Lead.objects.create(owner=self.user, title="Recovery", description="Test", source_url="https://example.com/recovery")

    def test_stale_sending_claims_become_uncertain(self):
        old = timezone.now() - timedelta(minutes=60)
        followup = FollowUp.objects.create(
            lead=self.lead,
            scheduled_at=old,
            message="follow up",
            status="sending",
        )
        outreach = Outreach.objects.create(
            lead=self.lead,
            medium="email",
            channel="email",
            message="outreach",
            status="sending",
        )
        FollowUp.objects.filter(pk=followup.pk).update(updated_at=old)
        Outreach.objects.filter(pk=outreach.pk).update(updated_at=old)

        result = recover_stale_outbound_claims(max_age_minutes=30)

        self.assertEqual(result, {"followups": 1, "outreach": 1})
        followup.refresh_from_db()
        outreach.refresh_from_db()
        self.assertEqual(followup.status, "send_uncertain")
        self.assertEqual(outreach.status, "send_uncertain")
