import json
from typing import Any

from django.conf import settings
from openai import OpenAI

from .acquisition import personalize_proposal
from .knowledge import PROFILE
from .models import ActivityLog

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
        int(getattr(getattr(usage, "input_tokens_details", None), "cached_tokens", 0) or 0)
        if usage else 0,
    )


def _validated_analysis(data):
    required={"relevant":bool,"match_score":int,"service_match":str,"requirements":list,"pain_points":list,"recommended_approach":str,"matching_projects":list,"confidence":int}
    if not isinstance(data,dict) or any(k not in data for k in required):
        raise ValueError("AI qualification response is missing required fields.")
    for key,kind in required.items():
        if not isinstance(data[key],kind):
            raise ValueError(f"AI qualification field {key} has an invalid type.")
    data["match_score"]=max(0,min(100,data["match_score"]))
    data["confidence"]=max(0,min(100,data["confidence"]))
    return data


def _validated_proposal(text):
    text=(text or "").strip()
    if not text or len(text)>12000:
        raise ValueError("AI proposal response is empty or unreasonably large.")
    return text


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
    try:
        data = _validated_analysis(json.loads(response.output_text))
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        ActivityLog.objects.create(lead=lead,event_type="ai.validation_error",message="AI qualification response failed validation; deterministic fallback used.",metadata={"error":str(exc),"model":settings.OPENAI_MODEL})
        return deterministic_analysis(lead)
    input_tokens, output_tokens, cached_tokens = _usage(response)
    data.update({
        "model": settings.OPENAI_MODEL,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    })
    return data


def generate_proposal(lead, analysis) -> str:
    if not settings.OPENAI_API_KEY:
        parts = personalize_proposal(lead, analysis)
        if getattr(lead,"client_id",None) and hasattr(lead.client,"intelligence") and lead.client.intelligence.recommended_approach:
            parts["approach"] = lead.client.intelligence.recommended_approach
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
        "client_intelligence": ({"summary":lead.client.intelligence.summary,"communication_style":lead.client.intelligence.communication_style,"preferences":lead.client.intelligence.preferences,"objections":lead.client.intelligence.objections,"recommended_approach":lead.client.intelligence.recommended_approach} if getattr(lead,"client_id",None) and hasattr(lead.client,"intelligence") else {}),
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
    return _validated_proposal(response.output_text)
