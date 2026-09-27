import json
import logging
from typing import Any

from django.conf import settings
from openai import OpenAI


logger = logging.getLogger(__name__)


class LiveDiscoveryError(Exception):
    pass


SYSTEM_PROMPT = """You are a live freelance opportunity discovery assistant.
Use the web search tool to find CURRENT, publicly available freelance or contract opportunities that match the developer profile and the user's search request.
Return ONLY valid JSON in this shape:
{
  "leads": [{
    "title": "string", "company": "string", "description": "string",
    "source": "string", "source_url": "https://...", "action_url": "https://...",
    "lead_type": "freelance|direct|startup|other", "budget_text": "string",
    "technologies": ["string"], "contact_info": {}
  }]
}
Rules:
- Prefer current opportunities with a verifiable public source URL.
- When the result exposes a distinct application/bid/contact URL, return it as action_url; otherwise omit it and let the system use source_url.
- Preserve the exact public URL supplied by the search result; never fabricate URL paths.
- Never invent a company, budget, contact, project, or URL.
- Do not claim a page is available unless the search result supports it.
- Do not target or bypass login-only/private content.
- Prefer official job/freelance listings and publicly accessible pages.
- Include evidence rows only when an exact excerpt and its URL are present in the search findings.
- Do not treat a model confidence estimate as verification; unsupported fields may have no evidence row.
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


def discover_live(query: str, context_size=None, domain_exclusions="") -> dict[str, Any]:
    if not settings.OPENAI_API_KEY:
        raise LiveDiscoveryError("OPENAI_API_KEY is required for live discovery.")

    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    prompt = {
        "profile": settings.FREELANCE_SEARCH_PROFILE,
        "query": query + (" " + domain_exclusions if domain_exclusions else ""),
        "search_rules": {
            "current_only": True,
            "public_sources_only": True,
            "exclude_login_only_sources": True,
            "max_results": settings.DISCOVERY_MAX_RESULTS,
            "domain_exclusions": domain_exclusions,
        },
    }

    try:
        # Web Search and JSON mode cannot be combined in one Responses API call.
        # First gather grounded search findings, then normalize them in a second
        # Responses API call that has no web_search tool and can use structured output.
        search_response = client.responses.create(
            model=settings.DISCOVERY_MODEL,
            tools=[{
                "type": "web_search",
                "search_context_size": context_size or settings.DISCOVERY_SEARCH_CONTEXT_SIZE,
                "external_web_access": True,
            }],
            tool_choice="required",
            input=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(prompt)},
            ],
        )

        search_text = (search_response.output_text or "").strip()
        if not search_text:
            raise LiveDiscoveryError("Live discovery returned no search findings.")

        extraction_schema = {
            "type": "object",
            "properties": {
                "leads": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "company": {"type": "string"},
                            "company_website": {"type": "string"},
                            "company_description": {"type": "string"},
                            "location": {"type": "string"},
                            "hiring_signal": {"type": "string"},
                            "description": {"type": "string"},
                            "source": {"type": "string"},
                            "source_url": {"type": "string"},
                            "action_url": {"type": "string"},
                            "lead_type": {
                                "type": "string",
                                "enum": ["freelance", "direct", "startup", "other"],
                            },
                            "budget_text": {"type": "string"},
                            "technologies": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "contact_info": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "email": {"type": "string"},
                                    "phone": {"type": "string"},
                                    "profile_url": {"type": "string"},
                                    "role": {"type": "string"},
                                },
                                "required": ["name", "email", "phone", "profile_url", "role"],
                                "additionalProperties": False,
                            },
                            "posted_at": {"type": "string"},
                            "expires_at": {"type": "string"},
                            "evidence": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "field": {"type": "string"},
                                        "value": {"type": "string"},
                                        "source_url": {"type": "string"},
                                        "excerpt": {"type": "string"},
                                    },
                                    "required": ["field", "value", "source_url", "excerpt"],
                                    "additionalProperties": False,
                                },
                            },
                        },
                        "required": [
                            "title", "company", "company_website", "company_description", "location", "hiring_signal", "description", "source",
                            "source_url", "action_url", "lead_type",
                            "budget_text", "technologies", "contact_info", "posted_at", "expires_at", "evidence",
                        ],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["leads"],
            "additionalProperties": False,
        }

        extraction_response = client.responses.create(
            model=settings.DISCOVERY_MODEL,
            input=[
                {
                    "role": "system",
                    "content": (
                        "Convert the grounded web-search findings into the requested schema. "
                        "Use only facts and URLs present in the findings. Never invent URLs, "
                        "companies, budgets, contacts, or opportunities. Return an empty "
                        "leads array when the findings do not contain suitable current opportunities."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps({
                        "search_request": prompt,
                        "search_findings": search_text,
                    }),
                },
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "live_discovery_result",
                    "strict": True,
                    "schema": extraction_schema,
                }
            },
        )

        payload = _extract_json(extraction_response.output_text or "")
    except LiveDiscoveryError:
        raise
    except Exception as exc:
        logger.exception("Live discovery provider request failed: %s", exc)
        raise LiveDiscoveryError("Live discovery provider request failed.") from exc

    leads = payload.get("leads", []) if isinstance(payload, dict) else []
    if not isinstance(leads, list):
        raise LiveDiscoveryError("Live discovery returned an invalid leads list.")

    cleaned = []
    for lead in leads:
        if not isinstance(lead, dict):
            cleaned.append(lead)
            continue
        lead["source"] = lead.get("source") or "web_search"
        lead["lead_type"] = lead.get("lead_type") or "freelance"
        lead["technologies"] = lead.get("technologies") or []
        lead["contact_info"] = lead.get("contact_info") or {}
        if lead.get("action_url") and isinstance(lead["action_url"], str):
            lead["action_url"] = lead["action_url"].strip()
        else:
            lead.pop("action_url", None)
        cleaned.append(lead)
        return {"leads": cleaned, "model": settings.DISCOVERY_MODEL, "search_findings": search_text}
