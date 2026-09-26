import json

from django.conf import settings
from openai import OpenAI

from .ai_service import generate_proposal
from .models import ActivityLog, Lead, LeadAnalysis, Proposal, ProposalVersion


REVISION_PROMPT = """Rewrite a freelance proposal using only the supplied proposal, lead and instruction.
Preserve factual claims. Do not invent clients, metrics, outcomes, technologies, prices or testimonials.
Keep it concise and client-focused. Return only the proposal text."""


def create_proposal(lead: Lead, analysis: LeadAnalysis, delivery_medium: str):
    content = generate_proposal(lead, analysis)
    proposal = Proposal.objects.create(lead=lead, delivery_medium=delivery_medium, current_version=1)
    version = ProposalVersion.objects.create(proposal=proposal, version_number=1, content=content, source="ai")
    return proposal, version


def current_version(proposal):
    return proposal.versions.filter(version_number=proposal.current_version).first() or proposal.versions.order_by("-version_number").first()


def revise_proposal(proposal, instruction: str, source="ai"):
    instruction = (instruction or "").strip()
    if not instruction:
        raise ValueError("A revision instruction is required.")
    current = current_version(proposal)
    if not current:
        raise ValueError("Proposal has no version.")
    if not settings.OPENAI_API_KEY:
        # Deterministic editing keeps the workspace usable without an API key.
        text = current.content
        if "short" in instruction.lower():
            text = "\n\n".join(text.split("\n\n")[:4])
        elif "technical" in instruction.lower():
            text = text + "\n\nImplementation focus: API design, validation, integration boundaries, testing, and maintainable delivery."
        elif "client" in instruction.lower():
            text = text.replace("I can help with", "For your project, I would help with")
        else:
            text = text + "\n\n" + instruction
    else:
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        payload = {
            "proposal": current.content,
            "lead": {"title": proposal.lead.title, "company": proposal.lead.company, "description": proposal.lead.description[:settings.AI_MAX_LEAD_DESCRIPTION_CHARS]},
            "instruction": instruction,
        }
        response = client.responses.create(
            model=settings.OPENAI_MODEL,
            input=[{"role":"system","content":REVISION_PROMPT},{"role":"user","content":json.dumps(payload,separators=(",",":"))}],
            max_output_tokens=settings.AI_PROPOSAL_MAX_OUTPUT_TOKENS,
        )
        text = response.output_text.strip()
        usage = getattr(response, "usage", None)
        ActivityLog.objects.create(
            lead=proposal.lead,
            event_type="ai.usage",
            message="Proposal revision AI usage recorded.",
            metadata={
                "operation":"proposal_revision",
                "model":settings.OPENAI_MODEL,
                "input_tokens":int(getattr(usage,"input_tokens",0) or 0) if usage else 0,
                "output_tokens":int(getattr(usage,"output_tokens",0) or 0) if usage else 0,
            },
        )
    number = proposal.versions.order_by("-version_number").values_list("version_number", flat=True).first() or 0
    version = ProposalVersion.objects.create(proposal=proposal, version_number=number + 1, content=text, source=source, instruction=instruction)
    proposal.current_version = version.version_number
    proposal.status = "draft"
    proposal.save(update_fields=["current_version","status","updated_at"])
    return version


def restore_version(proposal, version_number):
    version = proposal.versions.filter(version_number=version_number).first()
    if not version:
        raise ValueError("Proposal version not found.")
    proposal.current_version = version.version_number
    proposal.status = "draft"
    proposal.save(update_fields=["current_version","status","updated_at"])
    return version
