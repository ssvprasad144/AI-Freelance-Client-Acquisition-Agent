import json
from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from openai import OpenAI

from .models import FollowUp, FollowUpSequence, Lead, Reply
from .outreach_adapters import resolve_outreach_destination


FOLLOWUP_PROMPT = """Write a concise freelance follow-up based only on the opportunity and prior interaction.
Do not invent facts, urgency, deadlines, prices, client replies, or outcomes.
Keep it professional, useful, and low-pressure. Return only the message."""


def generate_followup_message(lead: Lead, step: int, previous_reply=None, previous_message=""):
    if not settings.OPENAI_API_KEY:
        if previous_reply:
            return "Thanks for the update. I’m happy to clarify the remaining points or discuss the next step whenever convenient."
        if step == 1:
            return f"Hi, just following up on the {lead.title} opportunity. I’d be happy to clarify the scope or share the next implementation step."
        return "Just checking in on my previous message. If the project is still active, I’d be glad to continue the conversation."

    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    payload = {
        "lead": {"title": lead.title, "company": lead.company, "description": lead.description[:settings.AI_MAX_LEAD_DESCRIPTION_CHARS]},
        "step": step,
        "previous_reply": previous_reply.message[:settings.AI_MAX_REPLY_CHARS] if previous_reply else "",
        "previous_message": previous_message[:2000],
    }
    response = client.responses.create(
        model=settings.OPENAI_MODEL,
        input=[{"role":"system","content":FOLLOWUP_PROMPT},{"role":"user","content":json.dumps(payload,separators=(",",":"))}],
        max_output_tokens=settings.AI_PROPOSAL_MAX_OUTPUT_TOKENS,
    )
    return response.output_text.strip()


def create_sequence(lead, delays_days=None, max_steps=3):
    delays = list(delays_days or [3, 5, 7])[:max(1, min(int(max_steps), 5))]
    destination=resolve_outreach_destination(lead)
    sequence = FollowUpSequence.objects.create(lead=lead, max_steps=len(delays), delays_days=delays, current_step=1, medium=destination.medium, action_type=destination.action_type, destination_url=destination.url or "")
    previous_reply = lead.replies.order_by("-created_at").first()
    message = generate_followup_message(lead, 1, previous_reply)
    scheduled = timezone.now() + timedelta(days=int(delays[0]))
    followup = FollowUp.objects.create(sequence=sequence, lead=lead, step_number=1, medium=sequence.medium, action_type=sequence.action_type, destination_url=sequence.destination_url, scheduled_at=scheduled, message=message, status="draft")
    return sequence, followup


def cancel_if_stopped(sequence):
    lead = sequence.lead
    if sequence.stop_on_reply and lead.replies.exists():
        sequence.status = "completed"
    if sequence.stop_on_terminal_status and lead.status in {"won", "lost", "archived"}:
        sequence.status = "completed"
    if sequence.status == "completed":
        FollowUp.objects.filter(sequence=sequence, status__in=["draft","approved","due"]).update(status="cancelled")
        sequence.save(update_fields=["status","updated_at"])
        return True
    return False


def schedule_next_step(followup):
    sequence = followup.sequence
    if not sequence or sequence.status != "active":
        return None
    if cancel_if_stopped(sequence):
        return None
    next_step = followup.step_number + 1
    if next_step > sequence.max_steps:
        sequence.current_step = followup.step_number
        sequence.status = "completed"
        sequence.save(update_fields=["current_step","status","updated_at"])
        return None
    delays = sequence.delays_days or [3, 5, 7]
    delay = int(delays[min(next_step - 1, len(delays) - 1)])
    previous_reply = sequence.lead.replies.order_by("-created_at").first()
    previous_message = followup.message
    message = generate_followup_message(sequence.lead, next_step, previous_reply, previous_message)
    next_followup = FollowUp.objects.create(
        sequence=sequence, lead=sequence.lead, step_number=next_step, medium=sequence.medium, action_type=sequence.action_type, destination_url=sequence.destination_url,
        scheduled_at=timezone.now() + timedelta(days=delay), message=message, status="draft",
    )
    sequence.current_step = next_step
    sequence.save(update_fields=["current_step","updated_at"])
    return next_followup
