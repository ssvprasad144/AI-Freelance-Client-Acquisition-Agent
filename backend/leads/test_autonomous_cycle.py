from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from .autonomous_cycle import _run_safe_actions, _should_run_discovery, run_autonomous_cycle
from .models import ActivityLog, Lead, LeadAnalysis


class AutonomousCycleTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="autonomous",
            password="pass123",
        )

    @override_settings(DISCOVERY_CRON_INTERVAL_SECONDS=21600)
    def test_discovery_is_not_due_after_recent_completion(self):
        ActivityLog.objects.create(
            event_type="discovery.completed",
            message="recent",
            metadata={},
        )
        self.assertFalse(_should_run_discovery())

    def test_safe_actions_are_the_only_automatic_actions(self):
        lead = Lead.objects.create(
            owner=self.user,
            title="Django automation",
            description="Build a Django automation system.",
            status="qualified",
            source="direct",
        )
        LeadAnalysis.objects.create(
            lead=lead,
            relevant=True,
            match_score=90,
            confidence=90,
        )

        with patch(
            "leads.autonomous_cycle.execute_action",
            return_value={
                "executed": True,
                "requires_approval": False,
                "action": "generate_proposal",
            },
        ) as execute:
            executed, blocked = _run_safe_actions(self.user)

        self.assertEqual(len(executed), 1)
        self.assertEqual(blocked, [])
        execute.assert_called_once()
        self.assertEqual(execute.call_args.kwargs["mode"], "automatic")

    @override_settings(DISCOVERY_CRON_INTERVAL_SECONDS=21600)
    def test_cycle_stops_at_human_approval_boundary(self):
        ActivityLog.objects.create(
            event_type="discovery.completed",
            message="recent",
            metadata={},
        )
        Lead.objects.create(
            owner=self.user,
            title="Qualified opportunity",
            description="A real project",
            status="proposal",
            source="direct",
        )

        with patch(
            "leads.autonomous_cycle.process_due_followups",
            return_value={"processed": 0, "due": 0, "sent": False},
        ):
            result = run_autonomous_cycle()

        self.assertEqual(result["pending_approval"], 0)
        self.assertEqual(result["actions_executed"], [])
        self.assertEqual(
            ActivityLog.objects.filter(
                event_type="automation.cycle.completed"
            ).count(),
            1,
        )
