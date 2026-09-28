import uuid

from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone

from leads.acquisition_orchestrator import build_queue, execute_action, recalculate_opportunities
from leads.followup_service import process_due_followups
from leads.models import ActivityLog, AcquisitionOpportunity, FollowUp

SAFE_AUTOMATIC_ACTIONS = {"qualify", "generate_proposal", "plan_outreach"}


def _owners():
    User = get_user_model()
    return list(
        User.objects.filter(acquisition_leads__isnull=False)
        .distinct()
        .order_by("id")
    )


def _should_run_discovery():
    interval = max(int(getattr(settings, "DISCOVERY_CRON_INTERVAL_SECONDS", 21600)), 60)
    last = ActivityLog.objects.filter(
        event_type="discovery.completed"
    ).order_by("-created_at").first()
    return last is None or (
        timezone.now() - last.created_at
    ).total_seconds() >= interval


def _run_safe_actions(owner, limit=20):
    executed = []
    blocked = []

    for opportunity in build_queue(limit=limit, owner=owner):
        action = opportunity.recommended_action
        if action not in SAFE_AUTOMATIC_ACTIONS:
            continue

        try:
            result = execute_action(
                opportunity,
                action,
                mode="automatic",
                approved=False,
            )
            if result.get("executed"):
                executed.append({
                    "opportunity_id": opportunity.id,
                    "lead_id": opportunity.lead_id,
                    "action": action,
                })
        except (ValueError, RuntimeError) as exc:
            blocked.append({
                "opportunity_id": opportunity.id,
                "lead_id": opportunity.lead_id,
                "action": action,
                "error": str(exc),
            })

    return executed, blocked


def run_autonomous_cycle():
    """Run one idempotent supervisor cycle and stop only at approval boundaries."""
    run_id = uuid.uuid4().hex
    started = timezone.now()
    discovery = None
    owners = _owners()
    actions = []
    blocked = []

    ActivityLog.objects.create(
        event_type="automation.cycle.started",
        message="Autonomous acquisition supervisor cycle started.",
        metadata={"run_id": run_id, "owners": [user.id for user in owners]},
    )

    try:
        if _should_run_discovery():
            from leads.discovery.profiles import select_profile
            from leads.discovery_cycle import run_discovery_cycle

            profile = select_profile(
                settings.DISCOVERY_QUERY_CACHE_TTL_HOURS,
                only_if_due=False,
            )
            discovery = run_discovery_cycle(
                query=profile["query"],
                source="live",
                qualification_limit=settings.AI_QUALIFICATION_MAX_LEADS_PER_CYCLE,
                profile_id=profile["id"],
                strategy_id=profile.get("strategy_id"),
            )

        for owner in owners:
            recalculate_opportunities(owner=owner)
            executed, failed = _run_safe_actions(owner)
            actions.extend(executed)
            blocked.extend(failed)

        followups = process_due_followups()
        pending_approval = (
            AcquisitionOpportunity.objects.filter(
                status="pending_approval",
                lead__owner__in=owners,
            ).count()
            if owners
            else 0
        )
        due_followups = (
            FollowUp.objects.filter(
                status="due",
                lead__owner__in=owners,
            ).count()
            if owners
            else 0
        )
        unresolved_outbound = list(
            FollowUp.objects.filter(
                status="send_uncertain",
                lead__owner__in=owners,
            ).values_list("id", flat=True)[:20]
        )

        result = {
            "run_id": run_id,
            "duration_ms": int(
                (timezone.now() - started).total_seconds() * 1000
            ),
            "discovery": discovery,
            "actions_executed": actions,
            "blocked_actions": blocked,
            "followups": followups,
            "pending_approval": pending_approval,
            "due_followups": due_followups,
            "unresolved_outbound_ids": unresolved_outbound,
        }
        ActivityLog.objects.create(
            event_type="automation.cycle.completed",
            message="Autonomous acquisition supervisor cycle completed.",
            metadata=result,
        )
        return result
    except Exception as exc:
        result = {
            "run_id": run_id,
            "duration_ms": int(
                (timezone.now() - started).total_seconds() * 1000
            ),
            "error": str(exc),
        }
        ActivityLog.objects.create(
            event_type="automation.cycle.failed",
            message="Autonomous acquisition supervisor cycle failed.",
            metadata=result,
        )
        raise
