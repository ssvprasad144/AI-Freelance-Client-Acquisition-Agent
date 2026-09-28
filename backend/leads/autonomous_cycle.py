import uuid

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from leads.acquisition_orchestrator import build_queue, execute_action, recalculate_opportunities
from leads.followup_service import process_due_followups
from leads.models import ActivityLog, AcquisitionOpportunity, FollowUp, SupervisorLease

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


def _claim_supervisor(run_id, ttl_seconds=None):
    now = timezone.now()
    if ttl_seconds is None:
        ttl_seconds = getattr(settings, "AUTONOMOUS_CYCLE_LEASE_SECONDS", 900)
    until = now + timezone.timedelta(seconds=max(int(ttl_seconds), 60))
    with transaction.atomic():
        lease, _ = SupervisorLease.objects.select_for_update().get_or_create(
            key="acquisition-supervisor"
        )
        if lease.locked_until and lease.locked_until > now:
            return False
        lease.run_id = run_id
        lease.locked_until = until
        lease.save(update_fields=["run_id", "locked_until", "updated_at"])
        return True


def _release_supervisor(run_id):
    with transaction.atomic():
        lease = SupervisorLease.objects.select_for_update().filter(
            key="acquisition-supervisor", run_id=run_id
        ).first()
        if lease:
            lease.run_id = ""
            lease.locked_until = None
            lease.save(update_fields=["run_id", "locked_until", "updated_at"])


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
        except Exception as exc:
            blocked.append({
                "opportunity_id": opportunity.id,
                "lead_id": opportunity.lead_id,
                "action": action,
                "error": str(exc),
            })

    return executed, blocked


def run_autonomous_cycle():
    """Run one isolated supervisor cycle; overlapping invocations are safely skipped."""
    run_id = uuid.uuid4().hex
    started = timezone.now()
    if not _claim_supervisor(run_id):
        return {"run_id": run_id, "skipped": True, "reason": "another supervisor cycle is already running"}

    actions, blocked, failures = [], [], []
    discovery = None
    followups = {"processed": 0, "sent": False}
    owners = []

    try:
        owners = _owners()
        ActivityLog.objects.create(
            event_type="automation.cycle.started",
            message="Autonomous acquisition supervisor cycle started.",
            metadata={"run_id": run_id, "owners": [user.id for user in owners]},
        )
        if _should_run_discovery():
            try:
                from leads.discovery.profiles import select_profile
                from leads.discovery_cycle import run_discovery_cycle
                profile = select_profile(settings.DISCOVERY_QUERY_CACHE_TTL_HOURS, only_if_due=False)
                discovery = run_discovery_cycle(
                    query=profile["query"], source="live",
                    qualification_limit=settings.AI_QUALIFICATION_MAX_LEADS_PER_CYCLE,
                    profile_id=profile["id"], strategy_id=profile.get("strategy_id"),
                )
            except Exception as exc:
                failures.append({"stage": "discovery", "error": str(exc)[:500]})
                ActivityLog.objects.create(
                    event_type="automation.discovery_failed",
                    message="Discovery failed; existing acquisition work will continue.",
                    metadata={"run_id": run_id, "error": str(exc)[:500]},
                )

        for owner in owners:
            try:
                recalculate_opportunities(owner=owner)
                executed, failed = _run_safe_actions(owner)
                actions.extend(executed)
                blocked.extend(failed)
            except Exception as exc:
                failures.append({"stage": "owner", "owner_id": owner.id, "error": str(exc)[:500]})
                ActivityLog.objects.create(
                    event_type="automation.owner_failed",
                    message="Owner processing failed; supervisor continued.",
                    metadata={"run_id": run_id, "owner_id": owner.id, "error": str(exc)[:500]},
                )

        try:
            followups = process_due_followups()
        except Exception as exc:
            failures.append({"stage": "followups", "error": str(exc)[:500]})
            followups = {"processed": 0, "sent": False, "error": str(exc)[:500]}
            ActivityLog.objects.create(
                event_type="automation.followups_failed",
                message="Follow-up processing failed; next cycle will retry.",
                metadata={"run_id": run_id, "error": str(exc)[:500]},
            )

        pending_approval = AcquisitionOpportunity.objects.filter(
            status="pending_approval", lead__owner__in=owners
        ).count() if owners else 0
        due_followups = FollowUp.objects.filter(
            status="due", lead__owner__in=owners
        ).count() if owners else 0
        unresolved_outbound = list(FollowUp.objects.filter(
            status="send_uncertain", lead__owner__in=owners
        ).values_list("id", flat=True)[:20]) if owners else []

        result = {
            "run_id": run_id, "skipped": False,
            "duration_ms": int((timezone.now() - started).total_seconds() * 1000),
            "discovery": discovery, "actions_executed": actions,
            "blocked_actions": blocked, "failures": failures,
            "followups": followups, "pending_approval": pending_approval,
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
        failure = {"run_id": run_id, "error": str(exc)[:500]}
        try:
            ActivityLog.objects.create(
                event_type="automation.cycle.failed",
                message="Autonomous acquisition supervisor cycle failed unexpectedly; the next scheduled cycle can retry.",
                metadata=failure,
            )
        except Exception:
            pass
        return {"run_id": run_id, "skipped": False, "failures": [failure]}
    finally:
        _release_supervisor(run_id)
