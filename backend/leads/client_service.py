import json
import re
from urllib.parse import urlsplit
from django.conf import settings
from django.utils import timezone
from openai import OpenAI
from .models import Client, Contact, Conversation, ConversationMessage, ClientIntelligence, Lead

CLIENT_PROMPT="""Build client intelligence only from supplied history. Return JSON with summary, communication_style, preferences, objections, recommended_approach, confidence. Never invent facts."""
def normalize_company(value):
    return re.sub(r"[^a-z0-9]+"," ",str(value or "").lower()).strip()
def extract_domain(lead):
    try:
        return urlsplit(lead.source_url or "").netloc.lower().removeprefix("www.")
    except Exception:
        return ""
def sync_lead_client(lead):
    company=(lead.company or "").strip()
    if not company:
        return None, None
    normalized=normalize_company(company)
    client,created=Client.objects.get_or_create(normalized_company=normalized,defaults={"company":company,"domain":extract_domain(lead)})
    if not created and not client.domain and extract_domain(lead):
        client.domain=extract_domain(lead); client.save(update_fields=["domain","updated_at"])
    lead.client=client
    info=lead.contact_info or {}
    email=str(info.get("email") or "").strip()
    profile=str(info.get("profile_url") or info.get("linkedin") or "").strip()
    name=str(info.get("name") or info.get("contact_name") or "").strip()
    role=str(info.get("role") or "").strip()
    contact=None
    if email:
        contact=Contact.objects.filter(client=client,email__iexact=email).first()
    if not contact and (email or profile or name):
        contact=Contact.objects.create(client=client,email=email,profile_url=profile,name=name,role=role,metadata=info)
    elif contact:
        updates=[]
        for field,value in [("profile_url",profile),("name",name),("role",role)]:
            if value and not getattr(contact,field): setattr(contact,field,value); updates.append(field)
        if updates: updates.append("updated_at"); contact.save(update_fields=updates)
    lead.contact=contact
    lead.save(update_fields=["client","contact","updated_at"])
    return client,contact

def ensure_conversation(client,lead,channel,contact=None):
    conversation=Conversation.objects.filter(client=client,lead=lead,channel=channel).order_by("-updated_at").first()
    if not conversation:
        conversation=Conversation.objects.create(client=client,lead=lead,contact=contact,channel=channel,last_interaction_at=timezone.now())
    elif contact and not conversation.contact_id:
        conversation.contact=contact; conversation.save(update_fields=["contact","updated_at"])
    return conversation

def record_message(client,lead,channel,direction,message,metadata=None,contact=None):
    conversation=ensure_conversation(client,lead,channel,contact)
    item=ConversationMessage.objects.create(conversation=conversation,direction=direction,message=message,metadata=metadata or {})
    conversation.last_interaction_at=timezone.now()
    conversation.status="waiting" if direction=="outbound" else "open"
    conversation.save(update_fields=["last_interaction_at","status","updated_at"])
    return item

def client_context(client):
    leads=list(client.leads.select_related("analysis").order_by("-created_at")[:20])
    replies=[r for lead in leads for r in lead.replies.order_by("-created_at")[:5]]
    meetings=list(client.meetings.order_by("-created_at")[:10])
    proposals=[p for lead in leads for p in lead.proposals.prefetch_related("versions").order_by("-updated_at")[:3]]
    return {
        "client":{"company":client.company,"domain":client.domain,"industry":client.industry,"notes":client.notes},
        "leads":[{"title":l.title,"status":l.status,"description":l.description[:1500],"technologies":l.technologies} for l in leads],
        "replies":[{"message":r.message[:1500],"intent":r.intent,"sentiment":r.sentiment,"next_action":r.next_action} for r in replies[:15]],
        "meetings":[{"status":m.status,"outcome":m.outcome,"next_action":m.next_action} for m in meetings],
        "proposals":[{"content":(p.versions.order_by("-version_number").first().content if p.versions.exists() else "")[:1800]} for p in proposals],
    }

def generate_client_intelligence(client):
    payload=client_context(client)
    if not settings.OPENAI_API_KEY:
        replies=payload["replies"]
        intents=[r["intent"] for r in replies if r["intent"]]
        objections=[r["message"] for r in replies if r["intent"] in {"pricing","negotiation","clarification"}][:3]
        style="direct" if any("price" in r["message"].lower() for r in replies) else "professional"
        data={"summary":f"{client.company} has {len(payload['leads'])} tracked opportunities and {len(replies)} recorded replies.","communication_style":style,"preferences":[], "objections":objections,"recommended_approach":"Reuse proven project evidence, address known objections early, and keep the next step concrete.","confidence":50,"model":"deterministic"}
    else:
        client_ai=OpenAI(api_key=settings.OPENAI_API_KEY)
        response=client_ai.responses.create(model=settings.OPENAI_MODEL,input=[{"role":"system","content":CLIENT_PROMPT},{"role":"user","content":json.dumps(payload,separators=(",",":"))}],max_output_tokens=settings.AI_PROPOSAL_MAX_OUTPUT_TOKENS)
        data=json.loads(response.output_text); data["model"]=settings.OPENAI_MODEL
    intelligence,created=ClientIntelligence.objects.update_or_create(client=client,defaults=data)
    return intelligence
