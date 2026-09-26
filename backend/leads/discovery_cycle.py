import re
from urllib.parse import urlsplit

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

from .ai_service import analyze_lead
from .discovery.profiles import normalize_query, select_profile
from .discovery.service import DiscoveryService
from .lead_optimizer import ai_skip_analysis, local_lead_score, should_ai_qualify
from .models import ActivityLog, DiscoveryQueryCache, DiscoverySearchStat, Lead, LeadAnalysis


def _normalize_title(value):
    return re.sub(r"\\s+", " ", re.sub(r"[^a-z0-9 ]", " ", str(value).lower())).strip()


def _normalize_url(value):
    try:
        parts = urlsplit(str(value).strip())
        return f"{parts.netloc.lower().removeprefix('www.')}{parts.path.rstrip('/')}"
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
            existing = Lead.objects.filter(normalized_url=normalized_url).first() or Lead.objects.filter(
                normalized_title=normalized_title,
                company__iexact=item.get("company", ""),
            ).first()
            if existing:
                existing.last_verified_at = timezone.now()
                if item.get("expires_at"):
                    existing.expires_at = item.get("expires_at")
                existing.save(update_fields=["last_verified_at", "expires_at", "updated_at"])
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


def _fresh_qualified_inventory():
    now = timezone.now()
    return Lead.objects.filter(status="qualified").filter(
        models.Q(expires_at__isnull=True) | models.Q(expires_at__gt=now)
    ).count()


def _daily_search_count():
    return ActivityLog.objects.filter(
        event_type="discovery.search",
        created_at__date=timezone.localdate(),
    ).count()


def _preview_score(item):
    preview = type(
        "LeadPreview", (), {
            "title": item.get("title", ""), "description": item.get("description", ""),
            "budget_text": item.get("budget_text", ""), "technologies": item.get("technologies") or [],
            "source_url": item.get("source_url", ""),
        }
    )()
    return local_lead_score(preview)


def _write_search_stat(profile_id, query, source, **values):
    return DiscoverySearchStat.objects.create(
        profile_id=profile_id, query=query, normalized_query=normalize_query(query),
        source=source, search_date=timezone.localdate(), **values,
    )


def _payload(query, profile_id, **extra):
    payload = {
        "query": query, "profile_id": profile_id, "source": "web_search",
        "model": settings.DISCOVERY_MODEL, "cached": False, "searched": False,
        "skip_reason": None, "discovered": 0, "created": 0, "duplicates": 0,
        "invalid": 0, "analyzed": 0, "qualified": 0, "locally_filtered": 0,
        "ai_calls": 0, "ai_input_tokens": 0, "ai_output_tokens": 0,
        "qualification_threshold": settings.QUALIFICATION_MIN_SCORE,
    }
    payload.update(extra)
    return payload


def run_discovery_cycle(query=None, source="live", qualification_limit=None, profile_id=None):
    cycle_started = timezone.now()
    if not query:
        profile = select_profile(settings.DISCOVERY_QUERY_CACHE_TTL_HOURS)
        query, profile_id = profile["query"], profile["id"]

    query = query.strip()
    normalized = normalize_query(query)
    profile_id = profile_id or "custom"
    cache = DiscoveryQueryCache.objects.filter(profile_id=profile_id, normalized_query=normalized).first()
    cache_fresh = bool(cache and cache.searched_at and cache.searched_at >= cycle_started - timezone.timedelta(hours=settings.DISCOVERY_QUERY_CACHE_TTL_HOURS))
    if cache_fresh:
        payload = _payload(query, profile_id, source=source, cached=True, skip_reason="fresh query cache")
        ActivityLog.objects.create(event_type="discovery.cache_hit", message="Discovery query served from freshness cache; no web search performed.", metadata=payload)
        return payload

    if source == "live":
        if _daily_search_count() >= settings.DISCOVERY_MAX_SEARCHES_PER_DAY:
            payload = _payload(query, profile_id, cached=True, skip_reason="daily web-search budget exhausted")
            ActivityLog.objects.create(event_type="discovery.skipped", message="Discovery search skipped: daily web-search budget exhausted.", metadata=payload)
            return payload
        if _fresh_qualified_inventory() >= settings.DISCOVERY_TARGET_QUALIFIED_LEADS:
            payload = _payload(query, profile_id, cached=True, skip_reason="qualified lead inventory is already healthy")
            ActivityLog.objects.create(event_type="discovery.skipped", message="Discovery search skipped: qualified lead inventory is already healthy.", metadata=payload)
            return payload
        ActivityLog.objects.create(event_type="discovery.search", message="Live discovery web search started.", metadata={"profile_id": profile_id, "query": query})

    result = DiscoveryService().discover(query, source)
    items = result.get("leads", [])
    raw_results = len(items)
    valid_results = sum(1 for item in items if item.get("title") and item.get("description") and item.get("source_url"))

    ranked, seen = [], set()
    for item in items:
        if not item.get("title") or not item.get("description") or not item.get("source_url"):
            continue
        key = _normalize_url(item["source_url"])
        if key in seen:
            continue
        seen.add(key)
        score = _preview_score(item)
        if score["service_hits"] and score["url_ok"]:
            ranked.append((score["score"], item))
    ranked.sort(key=lambda pair: pair[0], reverse=True)

    crawled_candidates = 0
    if settings.CRAWLER_ENABLED:
        crawl_candidates = [item for score, item in ranked if score >= settings.CRAWLER_MIN_LEAD_SCORE][:settings.CRAWLER_MAX_LEADS_PER_CYCLE]
        crawled_candidates = len(crawl_candidates)
        if crawl_candidates:
            from .discovery.public_crawler import enrich_leads
            enriched = enrich_leads(crawl_candidates, max_leads=len(crawl_candidates))
            enriched_by_url = {_normalize_url(item["source_url"]): item for item in enriched}
            items = [enriched_by_url.get(_normalize_url(item.get("source_url", "")), item) for item in items]

    created, duplicates, invalid = _store(items)
    DiscoveryQueryCache.objects.update_or_create(
        profile_id=profile_id, normalized_query=normalized,
        defaults={"query": query, "searched_at": timezone.now(), "result_count": len(items)},
    )

    limit = min(qualification_limit or settings.DISCOVERY_MAX_RESULTS, settings.AI_QUALIFICATION_MAX_LEADS_PER_CYCLE)
    now = timezone.now()
    candidates = list(Lead.objects.filter(status="new", analysis__isnull=True, discovered_at__gte=cycle_started).filter(
        models.Q(expires_at__isnull=True) | models.Q(expires_at__gt=now)
    ).order_by("-discovered_at", "-created_at")[:limit])

    analyzed = qualified = locally_filtered = 0
    ai_input_tokens = ai_output_tokens = 0
    for lead in candidates:
        local = local_lead_score(lead)
        if not should_ai_qualify(lead):
            data = ai_skip_analysis(lead, local); locally_filtered += 1
        else:
            data = analyze_lead(lead)
            ai_input_tokens += int(data.get("input_tokens", 0) or 0); ai_output_tokens += int(data.get("output_tokens", 0) or 0)
        analysis, _ = LeadAnalysis.objects.update_or_create(lead=lead, defaults=data)
        analyzed += 1
        if analysis.relevant and analysis.match_score >= settings.QUALIFICATION_MIN_SCORE:
            lead.status = "qualified"; lead.save(update_fields=["status", "updated_at"]); qualified += 1
            ActivityLog.objects.create(lead=lead, event_type="lead.auto_qualified", message=f"Lead auto-qualified with score {analysis.match_score}.", metadata={"model":analysis.model,"match_score":analysis.match_score,"threshold":settings.QUALIFICATION_MIN_SCORE})

    payload = _payload(query, profile_id, source=result.get("source", source), model=result.get("model", "unknown"), cached=False,
        searched=source == "live", discovered=len(items), created=created, duplicates=duplicates, invalid=invalid,
        analyzed=analyzed, qualified=qualified, locally_filtered=locally_filtered, ai_calls=analyzed-locally_filtered,
        ai_input_tokens=ai_input_tokens, ai_output_tokens=ai_output_tokens, raw_results=raw_results,
        valid_results=valid_results, unique_results=len(seen), scored_candidates=len(ranked), crawled_candidates=crawled_candidates)

    if source == "live":
        _write_search_stat(profile_id, query, result.get("source", "web_search"), raw_results=raw_results,
            valid_results=valid_results, unique_results=len(seen), scored_candidates=len(ranked), crawled_candidates=crawled_candidates,
            newly_created_leads=created, duplicates=duplicates, locally_filtered=locally_filtered,
            ai_calls=analyzed-locally_filtered, analyzed=analyzed, qualified=qualified)

    ActivityLog.objects.create(event_type="ai.usage", message="Discovery AI usage recorded.", metadata={"operation":"qualification","model":result.get("model","unknown"),"ai_calls":analyzed-locally_filtered,"input_tokens":ai_input_tokens,"output_tokens":ai_output_tokens})
    ActivityLog.objects.create(event_type="discovery.completed", message=f"Discovery cycle completed: {created} new leads, {qualified} qualified.", metadata=payload)
    return payload
