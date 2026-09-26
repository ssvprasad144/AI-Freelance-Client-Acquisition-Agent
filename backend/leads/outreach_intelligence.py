from django.utils import timezone
from .models import Lead, OutreachPlan

CHANNELS={"email":{"automatic":True,"action":"send_email"},"linkedin":{"automatic":False,"action":"manual_submit"},"marketplace":{"automatic":False,"action":"manual_submit"},"contact_form":{"automatic":False,"action":"manual_submit"},"community":{"automatic":False,"action":"manual_submit"}}
STOP_STATUSES={"replied","won","lost","archived"}

def choose_channel(lead):
    medium=(lead.outreach.order_by("-created_at").values_list("medium",flat=True).first() or "").lower()
    if medium in CHANNELS:return medium
    if (lead.contact_info or {}).get("email"):return "email"
    return "marketplace" if lead.action_url else "manual"

def personalized_message(lead,channel,variant="A"):
    intelligence=getattr(lead.client,"intelligence",None) if lead.client_id else None
    style=intelligence.communication_style if intelligence else ""
    approach=intelligence.recommended_approach if intelligence else ""
    intro=f"Hi {(lead.contact_info or {}).get('name') or 'there'},"
    value=f"I can help with {lead.title.lower()} using a practical Django/React and AI automation approach."
    proof=" I’ve built AI interview, automation, and full-stack products with Django, React and PostgreSQL."
    ask=" If this is still active, I’d be happy to discuss the scope and next steps."
    if variant=="B": value=f"Your {lead.title.lower()} looks like a strong fit for an AI-assisted implementation."
    if approach:value+=f" {approach[:220]}"
    if style and "concise" in style.lower(): ask=" Open to a short discussion this week?"
    return "\n\n".join([intro,value+proof,ask])

def create_plan(lead,channel=None,variant="A"):
    channel=channel or choose_channel(lead)
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
    plan.status="approved"; plan.approved_at=timezone.now(); plan.save(update_fields=["status","approved_at","updated_at"])
    return plan
