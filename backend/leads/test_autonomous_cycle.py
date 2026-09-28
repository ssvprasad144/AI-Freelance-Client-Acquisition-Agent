from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from datetime import timedelta

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


    def test_low_score_analysis_cannot_be_auto_qualified(self):
        from .models import Lead, LeadAnalysis
        lead = Lead.objects.create(
            owner=self.user,
            title="Poor fit",
            description="Unrelated work",
            source_url="https://example.com/poor-fit",
            status="new",
        )
        LeadAnalysis.objects.create(
            lead=lead,
            relevant=False,
            match_score=10,
            confidence=90,
        )
        from .acquisition_orchestrator import ensure_opportunity
        opportunity = ensure_opportunity(lead)
        self.assertEqual(opportunity.recommended_action, "review")
        with self.assertRaises(ValueError):
            from .acquisition_orchestrator import execute_action
            execute_action(opportunity, "qualify", mode="automatic")
        lead.refresh_from_db()
        self.assertEqual(lead.status, "new")


    def test_supervisor_skips_when_another_cycle_holds_lease(self):
        from .models import SupervisorLease
        SupervisorLease.objects.create(
            key="acquisition-supervisor",
            run_id="other-run",
            locked_until=timezone.now() + timedelta(minutes=5),
        )
        result = run_autonomous_cycle()
        self.assertTrue(result["skipped"])
        self.assertEqual(
            ActivityLog.objects.filter(event_type="automation.cycle.started").count(),
            0,
        )

    def test_supervisor_releases_lease_after_unexpected_failure(self):
        from .models import SupervisorLease
        lease = SupervisorLease.objects.create(key="acquisition-supervisor")
        with patch(
            "leads.autonomous_cycle._owners",
            side_effect=RuntimeError("owner lookup failed"),
        ):
            result = run_autonomous_cycle()
        lease.refresh_from_db()
        self.assertFalse(lease.locked_until)
        self.assertEqual(lease.run_id, "")
        self.assertEqual(len(result["failures"]), 1)
        self.assertEqual(result["failures"][0]["stage"] if "stage" in result["failures"][0] else "unexpected", "unexpected")

    def test_discovery_failure_does_not_stop_cycle(self):
        with patch(
            "leads.autonomous_cycle._should_run_discovery",
            return_value=True,
        ), patch(
            "leads.discovery_cycle.run_discovery_cycle",
            side_effect=RuntimeError("provider unavailable"),
        ), patch(
            "leads.autonomous_cycle.process_due_followups",
            return_value={"processed": 0, "due": 0, "sent": False},
        ):
            result = run_autonomous_cycle()
        self.assertEqual(len(result["failures"]), 1)
        self.assertEqual(result["failures"][0]["stage"], "discovery")
        self.assertEqual(
            ActivityLog.objects.filter(event_type="automation.cycle.completed").count(),
            1,
        )
