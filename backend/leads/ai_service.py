import json
from typing import Any

from django.conf import settings
from openai import OpenAI

from .acquisition import personalize_proposal
from .knowledge import PROFILE

SYSTEM_PROMPT = """You are a careful freelance lead qualification assistant.
Analyze the supplied lead against the developer profile.
Return ONLY JSON with:
relevant (boolean), match_score (0-100), service_match (string),
requirements (array), pain_points (array), recommended_approach (string),
matching_projects (array), confidence (0-100).
Use only supplied facts. Never invent clients, outcomes, metrics, integrations, budgets, or requirements.
Be concise.
"""

PROPOSAL_SYSTEM_PROMPT = """Draft a concise, professional freelance proposal from the supplied evidence.
Use only facts in the supplied profile, lead, and analysis.
Never invent clients, outcomes, metrics, testimonials, integrations, or sent messages.
Tie the opening to the client's stated requirement, cite only matching projects, and end with one concrete low-friction next step.
Keep it under 180 words.
"""


def deterministic_analysis(lead) -> dict[str, Any]:
    text = " ".join([lead.title, lead.description, lead.budget_text, " ".join(lead.technologies)]).lower()
    mapping = {
        "ai": ("AI Products", ["AI Business Automation Dashboard", "AI Interview"]),
        "automation": ("Business Automation", ["AI Business Automation Dashboard"]),
        "django": ("Full-Stack Development", ["CareerInnTech", "AI Interview"]),
        "react": ("Full-Stack Development", ["3D Motion Portfolio", "AI Business Automation Dashboard"]),
        "three.js": ("Interactive Web", ["3D Motion Portfolio"]),
        "three": ("Interactive Web", ["3D Motion Portfolio"]),
        "api": ("Full-Stack Development", ["CareerInnTech", "AI Business Automation Dashboard"]),
    }
    hits = [(svc, projects) for key, (svc, projects) in mapping.items() if key in text]
    projects = []
    for _, project_list in hits:
        for project in project_list:
            if project not in projects:
                projects.append(project)
    return {
        "relevant": bool(hits),
        "match_score": min(95, 30 + len(hits) * 15),
        "service_match": hits[0][0] if hits else "Needs review",
        "requirements": lead.technologies,
        "pain_points": ["Clarify scope, constraints, and delivery expectations."],
        "recommended_approach": "Confirm requirements, define the smallest deliverable, then propose an implementation plan grounded in existing project evidence.",
        "matching_projects": projects[:4],
        "confidence": 60 if hits else 30,
        "model": "deterministic-fallback",
        "input_tokens": 0,
        "output_tokens": 0,
    }


def _usage(response):
    usage = getattr(response, "usage", None)
    return (
        int(getattr(usage, "input_tokens", 0) or 0) if usage else 0,
        int(getattr(usage, "output_tokens", 0) or 0) if usage else 0,
        int(getattr(usage, "input_tokens_details", None).cached_tokens or 0)
        if usage and getattr(usage, "input_tokens_details", None) else 0,
    )


def analyze_lead(lead) -> dict[str, Any]:
    if not settings.OPENAI_API_KEY:
        return deterministic_analysis(lead)

    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    payload = {
        "profile": PROFILE,
        "lead": {
            "title": lead.title,
            "company": lead.company,
            "description": lead.description[: settings.AI_MAX_LEAD_DESCRIPTION_CHARS],
            "budget_text": lead.budget_text,
            "technologies": lead.technologies[:20],
            "lead_type": lead.lead_type,
        },
    }
    response = client.responses.create(
        model=settings.OPENAI_MODEL,
        input=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(payload, separators=(",", ":"))},
        ],
        max_output_tokens=settings.AI_QUALIFICATION_MAX_OUTPUT_TOKENS,
    )
    data = json.loads(response.output_text)
    input_tokens, output_tokens, cached_tokens = _usage(response)
    data.update({
        "model": settings.OPENAI_MODEL,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cached_input_tokens": cached_tokens,
    })
    return data


def generate_proposal(lead, analysis) -> str:
    if not settings.OPENAI_API_KEY:
        parts = personalize_proposal(lead, analysis)
        return "\n\n".join([parts["opening"], parts["fit"], parts["evidence"], parts["approach"], parts["next_step"], parts["closing"]])

    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    prompt = {
        "profile": PROFILE,
        "lead": {
            "title": lead.title,
            "company": lead.company,
            "description": lead.description[: settings.AI_MAX_LEAD_DESCRIPTION_CHARS],
            "budget_text": lead.budget_text,
            "technologies": lead.technologies[:20],
        },
        "analysis": {
            "service_match": analysis.service_match,
            "requirements": analysis.requirements[:12],
            "pain_points": analysis.pain_points[:6],
            "matching_projects": analysis.matching_projects[:4],
            "recommended_approach": analysis.recommended_approach,
        },
    }
    response = client.responses.create(
        model=settings.OPENAI_MODEL,
        input=[
            {"role": "system", "content": PROPOSAL_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(prompt, separators=(",", ":"))},
        ],
        max_output_tokens=settings.AI_PROPOSAL_MAX_OUTPUT_TOKENS,
    )
    input_tokens, output_tokens, cached_tokens = _usage(response)
    ActivityLog = __import__("leads.models", fromlist=["ActivityLog"]).ActivityLog
    ActivityLog.objects.create(
        lead=lead,
        event_type="ai.usage",
        message="Proposal AI usage recorded.",
        metadata={
            "operation": "proposal",
            "model": settings.OPENAI_MODEL,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cached_input_tokens": cached_tokens,
        },
    )
    return response.output_text
