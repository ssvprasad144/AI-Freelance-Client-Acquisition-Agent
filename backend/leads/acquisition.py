import json
import smtplib
from email.message import EmailMessage
from django.conf import settings
from django.utils import timezone
from openai import OpenAI
from .knowledge import PROFILE
from .models import ActivityLog, Lead, Outreach, Reply

REPLY_PROMPT="""Classify a client reply using only the supplied text.
Return JSON with keys: sentiment, intent, urgency, recommended_action.
sentiment must be one of positive, neutral, negative, mixed.
intent must be one of interested, pricing, portfolio, call, clarification, not_interested, follow_up_later, other.
urgency must be one of high, medium, low.
Never invent facts."""

def personalize_proposal(lead, analysis):
    evidence=", ".join(analysis.matching_projects or [])
    return {
        "opening": f"Hi{(' '+lead.company) if lead.company else ''},",
        "fit": f"I can help with the {lead.title.lower()} work, particularly around {analysis.service_match or 'full-stack and AI development'}.",
        "evidence": f"Relevant project evidence: {evidence or 'my portfolio projects relevant to this scope'}.",
        "approach": analysis.recommended_approach or "I would first confirm scope, constraints, integrations, and delivery expectations.",
        "next_step": "If useful, I can review the current requirements and outline the first implementation milestone.",
        "closing": "Regards,\nSSVPrasad",
    }

def classify_reply(reply):
    if not settings.OPENAI_API_KEY:
        text=reply.message.lower()
        if any(x in text for x in ["interested","let's talk","lets talk","schedule","call","available"]):
            return {"sentiment":"positive","intent":"interested","urgency":"medium","recommended_action":"Reply promptly and propose a concrete next step."}
        if any(x in text for x in ["price","pricing","cost","budget","quote"]):
            return {"sentiment":"neutral","intent":"pricing","urgency":"medium","recommended_action":"Clarify scope before giving a firm quote."}
        if any(x in text for x in ["no thanks","not interested","filled","already hired"]):
            return {"sentiment":"negative","intent":"not_interested","urgency":"low","recommended_action":"Close the lead politely and do not continue contacting unless invited."}
        return {"sentiment":"neutral","intent":"other","urgency":"low","recommended_action":"Review the reply and determine whether clarification is needed."}
    client=OpenAI(api_key=settings.OPENAI_API_KEY)
    response=client.responses.create(model=settings.OPENAI_MODEL,input=[{"role":"system","content":REPLY_PROMPT},{"role":"user","content":reply.message}])
    return json.loads(response.output_text)

def send_email(outreach):
    if outreach.status!="approved":
        raise ValueError("Only approved outreach can be sent.")
    lead=outreach.lead
    recipient=(lead.contact_info or {}).get("email")
    if not recipient:
        raise ValueError("Lead has no verified email contact.")
    if not getattr(settings,"OUTREACH_ENABLED",False):
        raise ValueError("Outbound sending is disabled. Enable it explicitly after configuring email.")
    message=EmailMessage()
    message["Subject"]=f"Re: {lead.title}"
    message["From"]=settings.OUTREACH_FROM_EMAIL
    message["To"]=recipient
    message.set_content(outreach.message)
    with smtplib.SMTP(settings.SMTP_HOST,settings.SMTP_PORT,timeout=20) as server:
        if settings.SMTP_USE_TLS: server.starttls()
        if settings.SMTP_USERNAME: server.login(settings.SMTP_USERNAME,settings.SMTP_PASSWORD)
        server.send_message(message)
    outreach.status="sent"; outreach.sent_at=timezone.now(); outreach.save(update_fields=["status","sent_at"])
    lead.status="contacted"; lead.save(update_fields=["status","updated_at"])
    ActivityLog.objects.create(lead=lead,event_type="outreach.sent",message="Approved outreach sent through configured email provider.",metadata={"outreach_id":outreach.id,"channel":outreach.channel})
    return {"sent":True,"outreach_id":outreach.id}


def send_followup(followup):
    if followup.status!="due":
        raise ValueError("Only due follow-ups can be sent.")
    recipient=(followup.lead.contact_info or {}).get("email")
    if not recipient:
        raise ValueError("Lead has no verified email contact.")
    if not getattr(settings,"OUTREACH_ENABLED",False):
        raise ValueError("Outbound sending is disabled. Enable it explicitly after configuring email.")
    message=EmailMessage()
    message["Subject"]=f"Following up: {followup.lead.title}"
    message["From"]=settings.OUTREACH_FROM_EMAIL
    message["To"]=recipient
    message.set_content(followup.message)
    with smtplib.SMTP(settings.SMTP_HOST,settings.SMTP_PORT,timeout=20) as server:
        if settings.SMTP_USE_TLS: server.starttls()
        if settings.SMTP_USERNAME: server.login(settings.SMTP_USERNAME,settings.SMTP_PASSWORD)
        server.send_message(message)
    followup.status="sent"; followup.sent_at=timezone.now(); followup.save(update_fields=["status","sent_at"])
    ActivityLog.objects.create(lead=followup.lead,event_type="followup.sent",message="Approved due follow-up sent through configured email provider.",metadata={"followup_id":followup.id})
    return {"sent":True,"followup_id":followup.id}
