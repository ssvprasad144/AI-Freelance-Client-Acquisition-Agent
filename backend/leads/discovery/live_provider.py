import json
from typing import Any

from django.conf import settings
from openai import OpenAI


class LiveDiscoveryError(Exception):
    pass


SYSTEM_PROMPT = """You are a live freelance opportunity discovery assistant.
Use the web search tool to find CURRENT, publicly available freelance or contract opportunities that match the developer profile and the user's search request.
Return ONLY valid JSON in this shape:
{
  "leads": [{
    "title": "string", "company": "string", "description": "string",
    "source": "string", "source_url": "https://...",
    "lead_type": "freelance|direct|startup|other", "budget_text": "string",
    "technologies": ["string"], "contact_info": {}
  }]
}
Rules:
- Prefer current opportunities with a verifiable public source URL.
- Never invent a company, budget, contact, project, or URL.
- Do not claim a page is available unless the search result supports it.
- Do not target or bypass login-only/private content.
- Prefer official job/freelance listings and publicly accessible pages.
- Return an empty list when there are no suitable current results.
"""


def _extract_json(text: str) -> dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start:end + 1])
        raise


def discover_live(query: str) -> dict[str, Any]:
    if not settings.OPENAI_API_KEY:
        raise LiveDiscoveryError("OPENAI_API_KEY is required for live discovery.")
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    prompt = {
        "profile": settings.FREELANCE_SEARCH_PROFILE,
        "query": query,
        "search_rules": {
            "current_only": True,
            "public_sources_only": True,
            "exclude_login_only_sources": True,
            "max_results": settings.DISCOVERY_MAX_RESULTS,
        },
    }
    response = client.responses.create(
        model=settings.DISCOVERY_MODEL,
        tools=[{
            "type": "web_search",
            "search_context_size": settings.DISCOVERY_SEARCH_CONTEXT_SIZE,
            "external_web_access": True,
        }],
        tool_choice="required",
        input=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(prompt)},
        ],
    )
    try:
        payload = _extract_json(response.output_text)
    except (TypeError, json.JSONDecodeError) as exc:
        raise LiveDiscoveryError("Live discovery returned invalid structured data.") from exc
    leads = payload.get("leads", []) if isinstance(payload, dict) else []
    if not isinstance(leads, list):
        raise LiveDiscoveryError("Live discovery returned an invalid leads list.")
    cleaned = []
    for lead in leads:
        if not isinstance(lead, dict) or not lead.get("title") or not lead.get("description") or not lead.get("source_url"):
            continue
        lead["source"] = lead.get("source") or "web_search"
        lead["lead_type"] = lead.get("lead_type") or "freelance"
        lead["technologies"] = lead.get("technologies") or []
        lead["contact_info"] = lead.get("contact_info") or {}
        cleaned.append(lead)
    return {"leads": cleaned, "model": settings.DISCOVERY_MODEL}
