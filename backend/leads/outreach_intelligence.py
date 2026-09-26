from django.utils import timezone
from django.conf import settings
from .models import Lead, OutreachPlan, Outreach

CHANNELS={"email":{"automatic":True,"action":"send_email"},"linkedin":{"automatic":False,"action":"manual_submit"},"marketplace":{"automatic":False,"action":"manual_submit"},"contact_form":{"automatic":False,"action":"manual_submit"},"community":{"automatic":False,"action":"manual_submit"}}
STOP_STATUSES={"replied","won","lost","archived"}

def choose_channel(lead):
    medium=(lead.outreach.order_by("-created_at").values_list("medium",flat=True).first() or "").lower()
    if medium in CHANNELS:return medium
    if (lead.contact_info or {}).get("email"):    return "\n\n".join([intro, value + proof, ask])

def create_plan(lead,channel=None,variant="A"):
    if not eligible(lead): raise ValueError("Outreach is blocked because this lead has replied, has a meeting, or is terminal.")
    channel=channel or choose_channel(lead)
    existing=OutreachPlan.objects.filter(lead=lead,channel=channel,variant=variant).first()
    if existing and existing.status in {"approved","sent"}:
        return existing
    plan,_=OutreachPlan.objects.update_or_create(lead=lead,channel=channel,variant=variant,defaults={
        "message":personalized_message(lead,channel,variant),
        "destination_url":lead.action_url or lead.source_url,
        "automatic":CHANNELS.get(channel,{"automatic":False})["automatic"],
        "status":"draft",
        "last_reason":"Generated from lead and client context.",
    })
    return plan

def eligible(lead):
    if lead.status in STOP_STATUSES:return False
    if lead.replies.exists() or lead.meetings.filter(status__in=["requested","scheduled","completed"]).exists():return False
    return True

def build_outreach_plans(limit=50):
    rows=[]
    for lead in Lead.objects.filter(status__in=["qualified","proposal","contacted"]).select_related("client"):
        if eligible(lead):
            rows.append(create_plan(lead))
            if len(rows)>=limit:break
    return rows

def record_attempt_for_outreach(plan, attempted_at=None):
    """Record a delivered/submitted outreach attempt after the external action succeeds."""
    attempted_at = attempted_at or timezone.now()
    plan.attempt_count += 1
    plan.last_attempt_at = attempted_at
    plan.status = "sent"
    plan.sent_at = attempted_at
    plan.save(update_fields=["attempt_count","last_attempt_at","status","sent_at","updated_at"])
    return plan


def channel_metrics():
    from django.db.models import Count,Q
    return list(OutreachPlan.objects.values("channel").annotate(
        drafts=Count("id",filter=Q(status="draft")),approved=Count("id",filter=Q(status="approved")),
        sent=Count("id",filter=Q(status="sent")),replied=Count("lead__replies",distinct=True),
        meetings=Count("lead__meetings",filter=Q(lead__meetings__status__in=["requested","scheduled","completed"]),distinct=True),
        wins=Count("lead",filter=Q(lead__status="won"),distinct=True)
    ).order_by("-sent"))

def mark_approved(plan):
    if not eligible(plan.lead): raise ValueError("Outreach must stop because the lead has replied, progressed to a meeting, or reached a terminal state.")
    if plan.attempt_count >= int(getattr(settings,"OUTREACH_MAX_ATTEMPTS_PER_LEAD",3)):
        raise ValueError("Outreach fatigue protection: maximum attempts reached.")
    if plan.last_attempt_at:
        delay_hours=float(getattr(settings,"OUTREACH_MIN_DELAY_HOURS",48))
        if (timezone.now()-plan.last_attempt_at).total_seconds() < delay_hours*3600:
            raise ValueError("Outreach fatigue protection: minimum delay has not elapsed.")
    plan.status="approved"; plan.approved_at=timezone.now()
    plan.save(update_fields=["status","approved_at","updated_at"])
    existing=Outreach.objects.filter(lead=plan.lead,medium=plan.channel,message=plan.message,status__in=["draft","approved","opened"]).order_by("-created_at").first()
    if not existing:
        Outreach.objects.create(lead=plan.lead,channel=plan.channel,medium=plan.channel,
            action_type="send_email" if plan.channel=="email" else "manual_submit",
            message=plan.message,destination_url=plan.destination_url,status="approved")
    else:
        existing.status="approved"; existing.save(update_fields=["status"])
    return plan
