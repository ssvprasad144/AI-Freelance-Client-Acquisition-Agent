from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import ActivityLog, FollowUp, FollowUpSequence, Outreach
from .followup_intelligence import cancel_if_stopped


def recover_stale_outbound_claims(max_age_minutes=30):
    cutoff = timezone.now() - timedelta(minutes=max_age_minutes)
    recovered_followups = FollowUp.objects.filter(status="sending", created_at__lt=cutoff).update(status="due")
    recovered_outreach = Outreach.objects.filter(status="sending", created_at__lt=cutoff).update(status="approved")
    return {"followups": recovered_followups, "outreach": recovered_outreach}

def process_due_followups():
    now = timezone.now()
    recovery = recover_stale_outbound_claims()
    for sequence in FollowUpSequence.objects.filter(status="active").select_related("lead"):
        cancel_if_stopped(sequence)
    candidate_ids = list(
        FollowUp.objects.filter(
            status="approved",
            scheduled_at__lte=now,
        ).order_by("scheduled_at").values_list("id", flat=True)
    )
    processed = 0

    for followup_id in candidate_ids:
        with transaction.atomic():
            changed = FollowUp.objects.filter(
                pk=followup_id,
                status="approved",
                scheduled_at__lte=now,
            ).update(status="due")

            if not changed:
                continue

            followup = FollowUp.objects.select_related("lead").get(pk=followup_id)
            ActivityLog.objects.create(
                lead=followup.lead,
                event_type="followup.due",
                message=(
                    "Approved follow-up reached its scheduled time and is ready "
                    "for action. No message was sent."
                ),
                metadata={"followup_id": followup.id},
            )
            processed += 1

    return {
        "processed": processed,
        "due": FollowUp.objects.filter(status="due").count(),
        "sent": False,
        "recovered": recovery,
    }
