import re
from urllib.parse import urlsplit

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

from .ai_service import analyze_lead
from .discovery.profiles import (
    daily_search_limit, domain_exclusions, normalize_query, query_family,
    query_signature, query_similarity, reusable_cache, select_profile,
    preferred_search_window_open,
)
from .discovery.service import DiscoveryService
from .lead_optimizer import ai_skip_analysis, local_lead_score, should_ai_qualify
from .models import ActivityLog, DiscoveryDomainStat, DiscoveryQueryCache, DiscoverySearchStat, Lead, LeadAnalysis


def _normalize_title(value):
    return re.sub(r"\\s+", " ", re.sub(r"[^a-z0-9 ]", " ", str(value).lower())).strip()

def _normalize_url(value):
    try:
        parts=urlsplit(str(value).strip()); return f"{parts.netloc.lower().removeprefix('www.')}{parts.path.rstrip('/')}"
    except Exception: return str(value).strip().lower().rstrip("/")

def _domain(value):
    try: return urlsplit(str(value)).netloc.lower().removeprefix("www.")
    except Exception: return ""

def _store(items):
    created=duplicates=invalid=0
    with transaction.atomic():
        for item in items:
            if not item.get("title") or not item.get("description") or not item.get("source_url"): invalid+=1; continue
            nu=_normalize_url(item["source_url"]); nt=_normalize_title(item["title"])
            existing=Lead.objects.filter(normalized_url=nu).first() or Lead.objects.filter(normalized_title=nt,company__iexact=item.get("company","")).first()
            if existing:
                existing.last_verified_at=timezone.now()
                if item.get("expires_at"): existing.expires_at=item.get("expires_at")
                existing.save(update_fields=["last_verified_at","expires_at","updated_at"]); duplicates+=1; continue
            Lead.objects.create(title=item["title"],normalized_title=nt,normalized_url=nu,company=item.get("company",""),description=item["description"],source=item.get("source") or "web_search",source_url=item["source_url"],lead_type=item.get("lead_type","freelance"),budget_text=item.get("budget_text",""),technologies=item.get("technologies") or [],contact_info=item.get("contact_info") or {},discovered_at=timezone.now(),posted_at=item.get("posted_at") or None,expires_at=item.get("expires_at") or None,last_verified_at=timezone.now()); created+=1
    return created,duplicates,invalid

def _fresh_qualified_inventory():
    now=timezone.now(); cutoff=now-timezone.timedelta(hours=settings.DISCOVERY_FRESHNESS_HOURS)
    return Lead.objects.filter(status="qualified",last_verified_at__gte=cutoff).filter(models.Q(expires_at__isnull=True)|models.Q(expires_at__gt=now)).count()

def _daily_search_count():
    return ActivityLog.objects.filter(event_type="discovery.search",created_at__date=timezone.localdate()).count()

def _preview_score(item):
    preview=type("LeadPreview",(),{"title":item.get("title",""),"description":item.get("description",""),"budget_text":item.get("budget_text",""),"technologies":item.get("technologies") or [],"source_url":item.get("source_url","")})()
    return local_lead_score(preview)

def _write_search_stat(profile_id,strategy_id,query,source,**values):
    return DiscoverySearchStat.objects.create(profile_id=profile_id,strategy_id=strategy_id,query=query,normalized_query=normalize_query(query),source=source,search_date=timezone.localdate(),**values)

def _update_domain_stats(items,actual_search):
    domains={}
    for item in items:
        d=_domain(item.get("source_url",""))
        if d: domains[d]=domains.get(d,0)+1
    if not actual_search: return list(domains)
    now=timezone.now()
    for d,count in domains.items():
        stat,_=DiscoveryDomainStat.objects.get_or_create(domain=d)
        stat.searches+=1; stat.results+=count; stat.last_seen_at=now
        stat.save(update_fields=["searches","results","last_seen_at","updated_at"])
    return list(domains)

def _refresh_domain_outcomes(items):
    by_domain={}
    for item in items:
        d=_domain(item.get("source_url",""))
        if d: by_domain.setdefault(d,[]).append(_normalize_url(item.get("source_url","")))
    for d,urls in by_domain.items():
        leads=list(Lead.objects.filter(normalized_url__in=urls))
        qualified=sum(1 for lead in leads if lead.status in {"qualified","proposal","contacted","replied","won"})
        replied=sum(1 for lead in leads if lead.status in {"replied","won"})
        won=sum(1 for lead in leads if lead.status=="won")
        stat=DiscoveryDomainStat.objects.filter(domain=d).first()
        if stat:
            stat.qualified=max(stat.qualified,qualified); stat.replied=max(stat.replied,replied); stat.won=max(stat.won,won); stat.save(update_fields=["qualified","replied","won","updated_at"])

def _find_semantic_reuse(query,profile_id,strategy_id):
    cache=reusable_cache(query,profile_id=profile_id)
    if cache and cache.query_family.endswith(f":{strategy_id}") and query_similarity(query,cache.query)>=settings.DISCOVERY_SEMANTIC_REUSE_THRESHOLD:
        return cache
    return None

def _payload(query,profile_id,**extra):
    payload={"query":query,"profile_id":profile_id,"source":"web_search","model":settings.DISCOVERY_MODEL,"cached":False,"searched":False,"reused":False,"skip_reason":None,"discovered":0,"created":0,"duplicates":0,"invalid":0,"analyzed":0,"qualified":0,"locally_filtered":0,"ai_calls":0,"ai_input_tokens":0,"ai_output_tokens":0,"qualification_threshold":settings.QUALIFICATION_MIN_SCORE}; payload.update(extra); return payload

def run_discovery_cycle(query=None,source="live",qualification_limit=None,profile_id=None,strategy_id=None):
    cycle_started=timezone.now()
    selected=None
    if not query:
        selected=select_profile(settings.DISCOVERY_QUERY_CACHE_TTL_HOURS,strategy_id=strategy_id); query,profile_id,strategy_id=selected["query"],selected["id"],selected.get("strategy_id")
    query=query.strip(); normalized=normalize_query(query); profile_id=profile_id or "custom"; strategy_id=strategy_id or "general-web"
    cache=DiscoveryQueryCache.objects.filter(profile_id=profile_id,normalized_query=normalized).first()
    cache_fresh=bool(cache and cache.searched_at and cache.searched_at>=cycle_started-timezone.timedelta(hours=settings.DISCOVERY_QUERY_CACHE_TTL_HOURS))
    reused_cache=None
    if not cache_fresh and source=="live":
        reused_cache=_find_semantic_reuse(query,profile_id,strategy_id)
    if cache_fresh or reused_cache:
        source_cache=cache if cache_fresh else reused_cache
        items=list(source_cache.result_payload or [])
        if not items and cache_fresh:
            payload=_payload(query,profile_id,source=source,cached=True,skip_reason="fresh query cache",strategy_id=strategy_id); ActivityLog.objects.create(event_type="discovery.cache_hit",message="Discovery query served from freshness cache; no web search performed.",metadata=payload); return payload
        payload=_payload(query,profile_id,source=source,cached=True,reused=bool(reused_cache),skip_reason="semantic result reuse" if reused_cache else "fresh query cache",strategy_id=strategy_id)
        ActivityLog.objects.create(event_type="discovery.cache_hit",message="Discovery results reused without a new web search.",metadata=payload)
    elif source=="live":
        inventory=_fresh_qualified_inventory()
        if _daily_search_count()>=daily_search_limit(inventory):
            payload=_payload(query,profile_id,cached=True,skip_reason="dynamic daily web-search budget exhausted",strategy_id=strategy_id); ActivityLog.objects.create(event_type="discovery.skipped",message="Discovery search skipped: dynamic daily web-search budget exhausted.",metadata=payload); return payload
        if inventory>=settings.DISCOVERY_TARGET_QUALIFIED_LEADS:
            payload=_payload(query,profile_id,cached=True,skip_reason="fresh qualified lead inventory is already healthy",strategy_id=strategy_id); ActivityLog.objects.create(event_type="discovery.skipped",message="Discovery search skipped: fresh qualified lead inventory is already healthy.",metadata=payload); return payload
        if not preferred_search_window_open():
            payload=_payload(query,profile_id,cached=True,skip_reason="outside preferred discovery window",strategy_id=strategy_id); ActivityLog.objects.create(event_type="discovery.skipped",message="Discovery search deferred outside the preferred search window.",metadata=payload); return payload
        ActivityLog.objects.create(event_type="discovery.search",message="Live discovery web search started.",metadata={"profile_id":profile_id,"strategy_id":strategy_id,"query":query,"query_variant":(selected or {}).get("query_variant","base"),"context_size":(selected or {}).get("context_size",settings.DISCOVERY_SEARCH_CONTEXT_SIZE)})
        result=DiscoveryService().discover(query,source,context_size=(selected or {}).get("context_size"),domain_exclusions=(selected or {}).get("domain_exclusions") or domain_exclusions())
        items=result.get("leads",[])
    else:
        result=DiscoveryService().discover(query,source); items=result.get("leads",[])

    raw_results=len(items); valid_results=sum(1 for item in items if item.get("title") and item.get("description") and item.get("source_url"))
    ranked=[]; seen=set()
    for item in items:
        if not item.get("title") or not item.get("description") or not item.get("source_url"): continue
        key=_normalize_url(item["source_url"])
        if key in seen: continue
        seen.add(key); score=_preview_score(item)
        if score["service_hits"] and score["url_ok"]: ranked.append((score["score"],item))
    ranked.sort(key=lambda pair:pair[0],reverse=True)
    crawled_candidates=0
    if settings.CRAWLER_ENABLED:
        crawl_candidates=[item for score,item in ranked if score>=settings.CRAWLER_MIN_LEAD_SCORE][:settings.CRAWLER_MAX_LEADS_PER_CYCLE]; crawled_candidates=len(crawl_candidates)
        if crawl_candidates:
            from .discovery.public_crawler import enrich_leads
            enriched=enrich_leads(crawl_candidates,max_leads=len(crawl_candidates)); enriched_by_url={_normalize_url(item["source_url"]):item for item in enriched}; items=[enriched_by_url.get(_normalize_url(item.get("source_url","")),item) for item in items]
    created,duplicates,invalid=_store(items)
    domains=_update_domain_stats(items,actual_search=bool(source=="live" and not (cache_fresh or reused_cache)))
    cache_defaults={"query":query,"searched_at":timezone.now(),"result_count":len(items),"query_family":query_family(profile_id,strategy_id),"query_signature":query_signature(query),"result_payload":items[:settings.DISCOVERY_MAX_RESULTS],"source_domains":domains}
    DiscoveryQueryCache.objects.update_or_create(profile_id=profile_id,normalized_query=normalized,defaults=cache_defaults)
    limit=min(qualification_limit or settings.DISCOVERY_MAX_RESULTS,settings.AI_QUALIFICATION_MAX_LEADS_PER_CYCLE); now=timezone.now()
    candidates=list(Lead.objects.filter(status="new",analysis__isnull=True,discovered_at__gte=cycle_started).filter(models.Q(expires_at__isnull=True)|models.Q(expires_at__gt=now)).order_by("-discovered_at","-created_at")[:limit])
    analyzed=qualified=locally_filtered=0; ai_input_tokens=ai_output_tokens=0
    for lead in candidates:
        local=local_lead_score(lead)
        if not should_ai_qualify(lead): data=ai_skip_analysis(lead,local); locally_filtered+=1
        else:
            data=analyze_lead(lead); ai_input_tokens+=int(data.get("input_tokens",0) or 0); ai_output_tokens+=int(data.get("output_tokens",0) or 0)
        analysis,_=LeadAnalysis.objects.update_or_create(lead=lead,defaults=data); analyzed+=1
        if analysis.relevant and analysis.match_score>=settings.QUALIFICATION_MIN_SCORE:
            lead.status="qualified"; lead.save(update_fields=["status","updated_at"]); qualified+=1
            ActivityLog.objects.create(lead=lead,event_type="lead.auto_qualified",message=f"Lead auto-qualified with score {analysis.match_score}.",metadata={"model":analysis.model,"match_score":analysis.match_score,"threshold":settings.QUALIFICATION_MIN_SCORE})
    _refresh_domain_outcomes(items)
    actual_search=bool(source=="live" and not (cache_fresh or reused_cache))
    payload=_payload(query,profile_id,source=result.get("source",source) if 'result' in locals() else source,model=result.get("model","unknown") if 'result' in locals() else "cached",cached=not actual_search,searched=actual_search,reused=bool(reused_cache),discovered=len(items),created=created,duplicates=duplicates,invalid=invalid,analyzed=analyzed,qualified=qualified,locally_filtered=locally_filtered,ai_calls=analyzed-locally_filtered,ai_input_tokens=ai_input_tokens,ai_output_tokens=ai_output_tokens,raw_results=raw_results,valid_results=valid_results,unique_results=len(seen),scored_candidates=len(ranked),crawled_candidates=crawled_candidates,strategy_id=strategy_id,query_variant=(selected or {}).get("query_variant","base"),context_size=(selected or {}).get("context_size",settings.DISCOVERY_SEARCH_CONTEXT_SIZE))
    if actual_search:
        _write_search_stat(profile_id,strategy_id,query,result.get("source","web_search"),query_family=query_family(profile_id,strategy_id),query_variant=(selected or {}).get("query_variant","base"),source_domains=domains,context_size=(selected or {}).get("context_size",settings.DISCOVERY_SEARCH_CONTEXT_SIZE),raw_results=raw_results,valid_results=valid_results,unique_results=len(seen),scored_candidates=len(ranked),crawled_candidates=crawled_candidates,newly_created_leads=created,duplicates=duplicates,locally_filtered=locally_filtered,ai_calls=analyzed-locally_filtered,analyzed=analyzed,qualified=qualified)
    ActivityLog.objects.create(event_type="ai.usage",message="Discovery AI usage recorded.",metadata={"operation":"qualification","model":result.get("model","unknown") if 'result' in locals() else "cached","ai_calls":analyzed-locally_filtered,"input_tokens":ai_input_tokens,"output_tokens":ai_output_tokens})
    ActivityLog.objects.create(event_type="discovery.completed",message=f"Discovery cycle completed: {created} new leads, {qualified} qualified.",metadata=payload)
    return payload
