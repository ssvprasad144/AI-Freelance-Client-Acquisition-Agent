import re
from urllib.parse import urlsplit

from django.conf import settings


SERVICE_TERMS = {
    "AI Products": {"ai", "llm", "openai", "chatbot", "agent", "rag", "machine learning", "genai"},
    "Business Automation": {"automation", "workflow", "zapier", "make.com", "n8n", "webhook", "process automation"},
    "Full-Stack Development": {"django", "django rest", "drf", "python", "react", "javascript", "typescript", "api", "full stack", "full-stack"},
    "Interactive Web": {"three.js", "threejs", "webgl", "react three fiber", "3d web", "interactive website", "vite"},
}
INTENT_TERMS = {"freelance", "contract", "project", "developer", "development", "build", "mvp", "saas", "prototype", "hiring", "hire"}
EXCLUSION_TERMS = {"seo", "content writing", "data entry", "crypto trading", "adult", "gambling", "essay writing"}
MIN_TITLE_CHARS = 8
MIN_DESCRIPTION_CHARS = 40


def _text(lead):
    return " ".join(
        [
            str(getattr(lead, "title", "")),
            str(getattr(lead, "description", "")),
            str(getattr(lead, "budget_text", "")),
            " ".join(getattr(lead, "technologies", []) or []),
        ]
    ).lower()


def local_lead_score(lead):
    text = _text(lead)
    service_hits = {
        service: sorted(term for term in terms if term in text)
        for service, terms in SERVICE_TERMS.items()
    }
    service_hits = {k: v for k, v in service_hits.items() if v}
    intent_hits = sorted(term for term in INTENT_TERMS if term in text)
    exclusion_hits = sorted(term for term in EXCLUSION_TERMS if term in text)
    source_url = str(getattr(lead, "source_url", "")).strip()
    title = str(getattr(lead, "title", "")).strip()
    description = str(getattr(lead, "description", "")).strip()
    url_parts = urlsplit(source_url)
    url_ok = bool(url_parts.scheme in {"http", "https"} and url_parts.netloc)
    completeness = int(bool(title and len(title) >= MIN_TITLE_CHARS)) + int(len(description) >= MIN_DESCRIPTION_CHARS) + int(bool(getattr(lead, "company", "").strip()))

    score = 0
    score += min(55, sum(min(20, len(hits) * 8) for hits in service_hits.values()))
    score += min(25, len(intent_hits) * 5)
    score += min(6, len(service_hits) * 2)
    score += 10 if url_ok else 0
    score -= min(40, len(exclusion_hits) * 20)
    if not title or len(title) < MIN_TITLE_CHARS: score -= 20
    if len(description) < MIN_DESCRIPTION_CHARS: score -= 15
    if completeness < 2: score -= 10

    return {
        "score": max(0, min(100, score)),
        "service_hits": service_hits,
        "intent_hits": intent_hits,
        "exclusion_hits": exclusion_hits,
        "url_ok": url_ok,
        "completeness": completeness,
    }


def should_crawl_lead(lead):
    result = local_lead_score(lead)
    minimum = getattr(settings, "CRAWLER_MIN_LEAD_SCORE", 40)
    return result["score"] >= minimum and bool(result["service_hits"]) and result["url_ok"] and result["completeness"] >= 2


def should_ai_qualify(lead):
    result = local_lead_score(lead)
    minimum = getattr(settings, "LOCAL_PREFILTER_MIN_SCORE", 40)
    return result["score"] >= minimum and bool(result["service_hits"]) and result["url_ok"]


def ai_skip_analysis(lead, local):
    return {
        "relevant": False,
        "match_score": local["score"],
        "service_match": "Filtered locally",
        "requirements": list(getattr(lead, "technologies", []) or []),
        "pain_points": [],
        "recommended_approach": "Lead did not pass the deterministic relevance filter.",
        "matching_projects": [],
        "confidence": 95,
        "model": "local-prefilter",
        "input_tokens": 0,
        "output_tokens": 0,
    }
