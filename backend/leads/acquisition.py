import json
import smtplib
from email.message import EmailMessage
from django.conf import settings
from django.utils import timezone
from openai import OpenAI
from .knowledge import PROFILE
from .models import ActivityLog, Lead, Outreach, Reply

REPLY_PROMPT="""Classify a client reply using only the supplied text.
Return JSON with keys: sentiment, intent, urgency, confidence, extracted_questions, recommended_action, suggested_response, next_action.
sentiment must be one of positive, neutral, negative, mixed.
intent must be one of interested, pricing, portfolio, call, clarification, not_interested, follow_up_later, negotiation, other.
urgency must be one of high, medium, low. confidence must be 0-100. extracted_questions must be an array. next_action must be one of reply, schedule_call, clarify, negotiate, follow_up, close, review.
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
            return {"sentiment":"positive","intent":"interested","urgency":"medium","confidence":85,"extracted_questions":[],"recommended_action":"Reply promptly and propose a concrete next step.","suggested_response":"Thanks for getting back to me. I would be happy to discuss the scope and next steps.","next_action":"reply"}
        if any(x in text for x in ["price","pricing","cost","budget","quote"]):
            return {"sentiment":"neutral","intent":"pricing","urgency":"medium","confidence":80,"extracted_questions":[],"recommended_action":"Clarify scope before giving a firm quote.","suggested_response":"Happy to discuss pricing. I would first confirm the scope, deliverables, and timeline so I can give an accurate estimate.","next_action":"negotiate"}
        if any(x in text for x in ["no thanks","not interested","filled","already hired"]):
            return {"sentiment":"negative","intent":"not_interested","urgency":"low","confidence":90,"extracted_questions":[],"recommended_action":"Close the lead politely and do not continue contacting unless invited.","suggested_response":"Thanks for letting me know. I appreciate the response and wish you the best with the project.","next_action":"close"}
        return {"sentiment":"neutral","intent":"other","urgency":"low","confidence":50,"extracted_questions":[],"recommended_action":"Review the reply and determine whether clarification is needed.","suggested_response":"Thanks for the update. I will review the details and get back to you with the next step.","next_action":"review"}
    client=OpenAI(api_key=settings.OPENAI_API_KEY)
    response=client.responses.create(
        model=settings.OPENAI_MODEL,
        input=[{"role":"system","content":REPLY_PROMPT},{"role":"user","content":reply.message[:settings.AI_MAX_REPLY_CHARS]}],
        max_output_tokens=settings.AI_REPLY_MAX_OUTPUT_TOKENS,
    )
    usage=getattr(response,"usage",None)
    input_tokens=int(getattr(usage,"input_tokens",0) or 0) if usage else 0
    output_tokens=int(getattr(usage,"output_tokens",0) or 0) if usage else 0
    cached_details=getattr(usage,"input_tokens_details",None) if usage else None
    cached_tokens=int(getattr(cached_details,"cached_tokens",0) or 0) if cached_details else 0
    ActivityLog.objects.create(
        lead=reply.lead,
        event_type="ai.usage",
        message="Reply classification AI usage recorded.",
        metadata={"operation":"reply_classification","model":settings.OPENAI_MODEL,"input_tokens":input_tokens,"output_tokens":output_tokens,"cached_input_tokens":cached_tokens},
    )
    return json.loads(response.output_text)

def send_email(outreach):
    if outreach.medium != "email":
        raise ValueError("This outreach uses a manual platform action. Open its destination and submit it there.")
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
