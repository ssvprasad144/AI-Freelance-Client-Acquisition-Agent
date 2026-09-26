from django.conf import settings
from django.db import transaction
from django.utils import timezone
from .models import AcquisitionOpportunity, Lead, ActivityLog

STAGE_ACTIONS={
    "new": ("qualify","qualification"),
    "qualified": ("generate_proposal","proposal"),
    "proposal": ("approve_proposal","approval"),
    "contacted": ("await_reply","monitor"),
    "replied": ("book_meeting","meeting"),
}
TERMINAL={"won","lost","archived"}

def opportunity_score(lead):
    analysis=getattr(lead,"analysis",None)
    match=analysis.match_score if analysis else 0
    confidence=analysis.confidence if analysis else 0
    source_bonus={"direct":12,"startup":10,"freelance":8,"other":3}.get(lead.lead_type,3)
    budget_bonus=8 if lead.budget_text else 0
    tech_bonus=min(len(lead.technologies or [])*2,10)
    reply_bonus=20 if lead.status=="replied" else 0
    meeting_bonus=25 if lead.meetings.filter(status__in=["requested","scheduled"]).exists() else 0
    freshness=10 if lead.updated_at and (timezone.now()-lead.updated_at).total_seconds()<86400 else 0
    return min(100,round(match*0.55+confidence*0.10+source_bonus+budget_bonus+tech_bonus+reply_bonus+meeting_bonus+freshness))

def next_action(lead):
    if lead.status in TERMINAL: return {"action":"none","reason":"terminal lead"}
    if lead.replies.exists() and lead.status=="replied":
        if lead.meetings.filter(status__in=["requested","scheduled"]).exists():
            return {"action":"await_meeting","reason":"meeting already in progress"}
        return {"action":"book_meeting","reason":"reply received"}
    action,category=STAGE_ACTIONS.get(lead.status,("review","manual_review"))
    if lead.status=="new" and getattr(lead,"analysis",None): action="qualify"
    return {"action":action,"category":category}

def ensure_opportunity(lead):
    score=opportunity_score(lead); action=next_action(lead)
    obj,_=AcquisitionOpportunity.objects.update_or_create(lead=lead,defaults={"score":score,"recommended_action":action["action"],"action_category":action.get("category",""),"reason":action.get("reason",""),"stage":lead.status})
    return obj

def build_queue(limit=50):
    rows=[]
    for lead in Lead.objects.exclude(status__in=TERMINAL).select_related("analysis").prefetch_related("replies","meetings")[:500]:
        rows.append(ensure_opportunity(lead))
    rows.sort(key=lambda x:(x.score,-x.updated_at.timestamp()),reverse=True)
    return rows[:limit]

VALID_ACTIONS={
 "qualify":{"from":["new"],"to":"qualified"},
 "generate_proposal":{"from":["qualified"],"to":"proposal"},
 "approve_proposal":{"from":["proposal"],"to":"proposal"},
 "book_meeting":{"from":["replied"],"to":"replied"},
 "await_reply":{"from":["contacted"],"to":"contacted"},
 "await_meeting":{"from":["replied"],"to":"replied"},
 "review":{"from":["new","qualified","proposal","contacted","replied"],"to":None},
}

def execute_action(opportunity,action,mode=None,approved=False):
    mode=mode or getattr(settings,"ACQUISITION_AUTOMATION_MODE","approval_required")
    lead=opportunity.lead
    rule=VALID_ACTIONS.get(action)
    if not rule or lead.status not in rule["from"]:
        raise ValueError("Invalid action for the lead's current stage.")
    if mode=="approval_required" and not approved:
        opportunity.status="pending_approval"; opportunity.save(update_fields=["status","updated_at"])
        return {"executed":False,"requires_approval":True,"action":action}
    if action=="qualify":
        if not lead.analysis_id: raise ValueError("Analyze the lead before qualification.")
        lead.status="qualified"; lead.save(update_fields=["status","updated_at"])
    elif action=="generate_proposal":
        opportunity.status="pending_approval"; opportunity.save(update_fields=["status","updated_at"])
        return {"executed":False,"requires_approval":True,"action":action,"handoff":"proposal_generation"}
    elif action=="approve_proposal":
        if not lead.outreach.filter(status="draft").exists(): raise ValueError("Generate a proposal before approval.")
    elif action=="book_meeting":
        opportunity.status="pending_approval"; opportunity.save(update_fields=["status","updated_at"])
        return {"executed":False,"requires_approval":True,"action":action,"handoff":"meeting_booking"}
    opportunity.status="ready"; opportunity.stage=lead.status; opportunity.recommended_action=next_action(lead)["action"]; opportunity.executed_at=timezone.now(); opportunity.save(update_fields=["status","stage","recommended_action","executed_at","updated_at"])
    ActivityLog.objects.create(lead=lead,event_type="acquisition.action_executed",message=f"Acquisition action executed: {action}.",metadata={"opportunity_id":opportunity.id,"action":action,"mode":mode})
    return {"executed":True,"requires_approval":False,"action":action,"lead_status":lead.status,"opportunity_id":opportunity.id}

def recalculate_opportunities():
    count=0
    for lead in Lead.objects.exclude(status__in=TERMINAL):
        ensure_opportunity(lead); count+=1
    return {"updated":count}
