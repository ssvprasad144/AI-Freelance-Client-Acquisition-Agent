import re
import time
from urllib.parse import urlsplit

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .ai_service import analyze_lead
from .discovery.service import DiscoveryService
from .models import ActivityLog, Lead, LeadAnalysis
from .lead_optimizer import local_lead_score, should_ai_qualify, ai_skip_analysis


def _normalize_title(value):
    return re.sub(r"\\s+", " ", re.sub(r"[^a-z0-9 ]", " ", str(value).lower())).strip()


def _normalize_url(value):
    try:
        parts = urlsplit(str(value).strip())
        return f"{parts.netloc.lower().removeprefix('www.')}" + parts.path.rstrip("/")
    except Exception:
        return str(value).strip().lower().rstrip("/")


def _store(items):
    created = duplicates = invalid = 0
    with transaction.atomic():
        for item in items:
            if not item.get("title") or not item.get("description") or not item.get("source_url"):
                invalid += 1
                continue
            normalized_url = _normalize_url(item["source_url"])
            normalized_title = _normalize_title(item["title"])
            if Lead.objects.filter(normalized_url=normalized_url).exists():
                duplicates += 1
                continue
            if Lead.objects.filter(normalized_title=normalized_title, company__iexact=item.get("company", "")).exists():
                duplicates += 1
                continue
            Lead.objects.create(
                title=item["title"], normalized_title=normalized_title,
                normalized_url=normalized_url, company=item.get("company", ""),
                description=item["description"], source=item.get("source") or "web_search",
                source_url=item["source_url"], lead_type=item.get("lead_type", "freelance"),
                budget_text=item.get("budget_text", ""), technologies=item.get("technologies") or [],
                contact_info=item.get("contact_info") or {}, discovered_at=timezone.now(),
                posted_at=item.get("posted_at") or None, expires_at=item.get("expires_at") or None,
                last_verified_at=timezone.now(),
            )
            created += 1
    return created, duplicates, invalid


def run_discovery_cycle(query=None, source="live", qualification_limit=None):
    query = (query or settings.DEFAULT_DISCOVERY_QUERY).strip()
    result = DiscoveryService().discover(query, source)
    items = result.get("leads", [])
    created, duplicates, invalid = _store(items)
    limit = qualification_limit or settings.DISCOVERY_MAX_RESULTS
    candidates = list(Lead.objects.filter(status="new", analysis__isnull=True).order_by("-discovered_at", "-created_at")[:limit])
    analyzed = qualified = locally_filtered = 0
    ai_input_tokens = ai_output_tokens = 0
    for lead in candidates:
        local = local_lead_score(lead)
        if not should_ai_qualify(lead):
            data = ai_skip_analysis(lead, local)
            locally_filtered += 1
        else:
            data = analyze_lead(lead)
            ai_input_tokens += int(data.get("input_tokens", 0) or 0)
            ai_output_tokens += int(data.get("output_tokens", 0) or 0)
        analysis, _ = LeadAnalysis.objects.update_or_create(lead=lead, defaults=data)
        analyzed += 1
        if analysis.relevant and analysis.match_score >= settings.QUALIFICATION_MIN_SCORE:
            lead.status = "qualified"
            lead.save(update_fields=["status", "updated_at"])
            qualified += 1
            ActivityLog.objects.create(
                lead=lead, event_type="lead.auto_qualified",
                message=f"Lead auto-qualified with score {analysis.match_score}.",
                metadata={"model": analysis.model, "match_score": analysis.match_score,
                          "threshold": settings.QUALIFICATION_MIN_SCORE},
            )
    payload = {
        "query": query, "source": result.get("source", source), "model": result.get("model", "unknown"),
        "discovered": len(items), "created": created, "duplicates": duplicates, "invalid": invalid,
        "analyzed": analyzed, "qualified": qualified, "locally_filtered": locally_filtered,
        "ai_calls": analyzed - locally_filtered, "ai_input_tokens": ai_input_tokens, "ai_output_tokens": ai_output_tokens,
        "qualification_threshold": settings.QUALIFICATION_MIN_SCORE,
    }
    ActivityLog.objects.create(
        event_type="ai.usage",
        message="Discovery AI usage recorded.",
        metadata={"operation":"qualification","model":result.get("model","unknown"),"ai_calls":analyzed-locally_filtered,"input_tokens":ai_input_tokens,"output_tokens":ai_output_tokens},
    )
    ActivityLog.objects.create(
        event_type="discovery.completed",
        message=f"Discovery cycle completed: {created} new leads, {qualified} qualified.",
        metadata=payload,
    )
    return payload
