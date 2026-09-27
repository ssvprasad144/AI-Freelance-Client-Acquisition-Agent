import hashlib
import re
from urllib.parse import urlsplit

from django.conf import settings
from django.db import IntegrityError, models, transaction
from django.utils import timezone

from .ai_service import analyze_lead
from .discovery.profiles import (
    daily_search_limit, domain_exclusions, normalize_query, query_family,
    query_signature, query_similarity, reusable_cache, select_profile,
    preferred_search_window_open,
)
from .discovery.service import DiscoveryService
from .lead_optimizer import ai_skip_analysis, local_lead_score, should_ai_qualify
from .data_quality import normalize_url, validate_lead_record
from .models import ActivityLog, DiscoveryDomainStat, DiscoveryQueryCache, DiscoverySearchStat, Lead, LeadAnalysis, LeadEvidence


def _normalize_title(value):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", str(value).lower())).strip()

def _normalize_url(value):
    try:
        return normalize_url(value)
    except ValueError:
        return ""

def _domain(value):
    try: return urlsplit(str(value)).netloc.lower().removeprefix("www.")
    except Exception: return ""

def _store(items,profile_id="",strategy_id="",query="",search_findings="",source_findings=None,source_checked=False):
    created=duplicates=invalid=0
    for index,item in enumerate(items):
        try:
            normalized=validate_lead_record(item,source_findings if source_findings is not None else search_findings)
            nt=_normalize_title(normalized["title"])
            nu=normalized["source_url"]
            now=timezone.now()
            with transaction.atomic():
                existing=(Lead.objects.filter(normalized_url=nu).first() or
                          Lead.objects.filter(normalized_title=nt,company__iexact=normalized["company"]).exclude(company="").first())
                if existing:
                    updates=[]
                    if source_checked:
                        existing.last_checked_at=now; updates.append("last_checked_at")
                    if normalized.get("expires_at") and source_checked:
                        existing.expires_at=normalized["expires_at"]; updates.append("expires_at")
                    if normalized.get("posted_at") and source_checked and not existing.posted_at:
                        existing.posted_at=normalized["posted_at"]; updates.append("posted_at")
                    if normalized.get("action_url") and source_checked and existing.action_url == existing.source_url:
                        existing.action_url=normalized["action_url"]; updates.append("action_url")
                    if normalized.get("crawler_metadata"):
                        existing.last_verified_at=now; updates.append("last_verified_at")
                    if updates: existing.save(update_fields=[*updates,"updated_at"])
                    _save_evidence(existing,normalized.get("evidence",[]))
                    duplicates+=1
                    continue
                lead=Lead.objects.create(
                    title=normalized["title"],normalized_title=nt,normalized_url=nu,
                    company=normalized["company"],description=normalized["description"],
                    source=normalized.get("source") or "web_search",source_url=nu,
                    action_url=normalized.get("action_url") or nu,
                    company_website=normalized.get("company_website", ""),
                    location=normalized.get("location", ""),
                    company_description=normalized.get("company_description", ""),
                    hiring_signal=normalized.get("hiring_signal", ""),
                    lead_type=normalized.get("lead_type","freelance"),budget_text=normalized.get("budget_text",""),
                    technologies=normalized.get("technologies") or [],contact_info=normalized.get("contact_info") or {},
                    discovery_profile=profile_id,discovery_strategy=strategy_id,discovery_query=query,
                    discovered_at=now,posted_at=normalized.get("posted_at"),expires_at=normalized.get("expires_at"),
                    last_checked_at=now if source_checked else None,
                    last_verified_at=now if normalized.get("crawler_metadata") else None,
                )
                _save_evidence(lead,normalized.get("evidence",[]))
                created+=1
        except IntegrityError:
            # The normalized URL unique constraint is the final guard for concurrent runs.
            if Lead.objects.filter(normalized_url=locals().get("nu", "")).exists():
                duplicates+=1
            else:
                invalid+=1
                _record_invalid(index,item,"Database uniqueness conflict.")
        except Exception as exc:
            invalid+=1
            _record_invalid(index,item,str(exc))
    return created,duplicates,invalid


def _record_invalid(index,item,reason):
    ActivityLog.objects.create(event_type="discovery.record_rejected",message="A discovery record failed validation and was skipped.",metadata={"index":index,"source_url":str(item.get("source_url", ""))[:1000] if isinstance(item,dict) else "","reason":reason[:500]})


def _save_evidence(lead,evidence):
    supported={(row["field"],row["value"].casefold()) for row in evidence}
    for row in evidence:
        field_name,value=row["field"],row["value"]
        fingerprint=hashlib.sha256("\0".join((field_name,value,row["source_url"])).encode()).hexdigest()
        LeadEvidence.objects.get_or_create(
            lead=lead,evidence_hash=fingerprint,
            defaults={"field_name":field_name,"value":value,"source_url":row["source_url"],"excerpt":row["excerpt"],"origin":"extracted","validation_status":"valid" if field_name in {"source_url","action_url","company_website","contact_info.profile_url","contact_info.email"} else "pending","source_supported":True},
        )
    claims={
        "title":lead.title,"company":lead.company,"company_website":lead.company_website,
        "description":lead.description,"company_description":lead.company_description,
        "location":lead.location,"hiring_signal":lead.hiring_signal,"budget_text":lead.budget_text,
        "source_url":lead.source_url,"action_url":lead.action_url,
        "posted_at":lead.posted_at.isoformat() if lead.posted_at else "",
        "expires_at":lead.expires_at.isoformat() if lead.expires_at else "",
    }
    claims.update({f"contact_info.{key}":value for key,value in (lead.contact_info or {}).items() if value})
    claims.update({f"technologies.{index}":value for index,value in enumerate(lead.technologies or [])})
    for field_name,value in claims.items():
        if not value: continue
        value=str(value)
        is_supported=(field_name,value.casefold()) in supported
        source_row=next((row for row in evidence if row["field"]==field_name and row["value"].casefold()==value.casefold()),None)
        source_url=source_row["source_url"] if source_row else ""
        excerpt=source_row["excerpt"] if source_row else ""
        origin="extracted" if is_supported else "ai_inferred"
        validation_status="valid" if field_name in {"source_url","action_url","company_website","contact_info.profile_url","contact_info.email"} else "pending"
        fingerprint=hashlib.sha256("\0".join((field_name,value,source_url)).encode()).hexdigest()
        LeadEvidence.objects.get_or_create(
            lead=lead,evidence_hash=fingerprint,
            defaults={"field_name":field_name,"value":value,"source_url":source_url,"excerpt":excerpt,"origin":origin,"validation_status":validation_status,"source_supported":is_supported},
        )

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
            stat.qualified=max(stat.qualified,qualified); stat.replied=max(stat.replied,replied); stat.won=max(stat.won,won)
            if stat.results>=settings.DISCOVERY_DOMAIN_MIN_RESULTS and stat.qualified/max(stat.results,1)<settings.DISCOVERY_DOMAIN_BLOCK_QUALIFIED_RATE:
                stat.blocked_until=timezone.now()+timezone.timedelta(days=7)
            stat.save(update_fields=["qualified","replied","won","blocked_until","updated_at"])

def _find_semantic_reuse(query,profile_id,strategy_id):
    cache=reusable_cache(query,profile_id=profile_id)
    if cache and cache.query_family.endswith(f":{strategy_id}"):
        similarity=query_similarity(query,cache.query)
        if similarity>=settings.DISCOVERY_SEMANTIC_REUSE_THRESHOLD or (similarity>=0.5 and cache.profile_id==profile_id):
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
        result={"source":source,"model":"cached","leads":items,"search_findings":source_cache.search_findings or "","source_findings":source_cache.source_findings or []}
        if not items and cache_fresh:
            payload=_payload(query,profile_id,source=source,cached=True,skip_reason="fresh query cache",strategy_id=strategy_id); ActivityLog.objects.create(event_type="discovery.cache_hit",message="Discovery query served from freshness cache; no web search performed.",metadata=payload); return payload
        payload=_payload(query,profile_id,source=source,cached=True,reused=bool(reused_cache),skip_reason="semantic result reuse" if reused_cache else "fresh query cache",strategy_id=strategy_id)
        ActivityLog.objects.create(event_type="discovery.cache_hit",message="Discovery results reused without a new web search.",metadata=payload)
    elif source=="live":
        inventory=_fresh_qualified_inventory()
        if _daily_search_count()>=daily_search_limit(inventory):
            result={"source":source,"model":"cached","leads":[]}; items=[]; skipped_reason="dynamic daily web-search budget exhausted"
            ActivityLog.objects.create(event_type="discovery.skipped",message="Discovery search skipped: dynamic daily web-search budget exhausted.",metadata=_payload(query,profile_id,cached=True,skip_reason=skipped_reason,strategy_id=strategy_id))
        elif inventory>=settings.DISCOVERY_TARGET_QUALIFIED_LEADS:
            result={"source":source,"model":"cached","leads":[]}; items=[]; skipped_reason="fresh qualified lead inventory is already healthy"
            ActivityLog.objects.create(event_type="discovery.skipped",message="Discovery search skipped: fresh qualified lead inventory is already healthy.",metadata=_payload(query,profile_id,cached=True,skip_reason=skipped_reason,strategy_id=strategy_id))
        elif not preferred_search_window_open():
            result={"source":source,"model":"cached","leads":[]}; items=[]; skipped_reason="outside preferred discovery window"
            ActivityLog.objects.create(event_type="discovery.skipped",message="Discovery search deferred outside the preferred search window.",metadata=_payload(query,profile_id,cached=True,skip_reason=skipped_reason,strategy_id=strategy_id))
        else:
            skipped_reason=None
            ActivityLog.objects.create(event_type="discovery.search",message="Live discovery web search started.",metadata={"profile_id":profile_id,"strategy_id":strategy_id,"query":query,"query_variant":(selected or {}).get("query_variant","base"),"context_size":(selected or {}).get("context_size",settings.DISCOVERY_SEARCH_CONTEXT_SIZE)})
            result=DiscoveryService().discover(query,source,context_size=(selected or {}).get("context_size"),domain_exclusions=(selected or {}).get("domain_exclusions") or domain_exclusions())
            items=result.get("leads",[])
    else:
        result=DiscoveryService().discover(query,source); items=result.get("leads",[])

    raw_results=len(items); valid_results=sum(1 for item in items if isinstance(item,dict) and item.get("title") and item.get("description") and item.get("source_url"))
    ranked=[]; seen=set()
    for item in items:
        if not isinstance(item,dict) or not item.get("title") or not item.get("description") or not item.get("source_url"): continue
        key=_normalize_url(item["source_url"])
        if not key: continue
        if key in seen: continue
        seen.add(key); score=_preview_score(item)
        if score["service_hits"] and score["url_ok"]: ranked.append((score["score"],item))
    ranked.sort(key=lambda pair:pair[0],reverse=True)
    crawled_candidates=0
    if settings.CRAWLER_ENABLED:
        crawl_candidates=[item for score,item in ranked if score>=settings.CRAWLER_MIN_LEAD_SCORE][:settings.CRAWLER_MAX_LEADS_PER_CYCLE]; crawled_candidates=len(crawl_candidates)
        if crawl_candidates:
            from .discovery.public_crawler import enrich_leads
            enriched=enrich_leads(crawl_candidates,max_leads=len(crawl_candidates)); enriched_by_url={_normalize_url(item["source_url"]):item for item in enriched if _normalize_url(item.get("source_url",""))}; items=[enriched_by_url.get(_normalize_url(item.get("source_url","")),item) for item in items]
    actual_search=bool(source=="live" and not (cache_fresh or reused_cache) and not (locals().get("skipped_reason")))
    created,duplicates,invalid=_store(items,profile_id=profile_id,strategy_id=strategy_id,query=query,search_findings=result.get("search_findings","") if "result" in locals() else "",source_findings=result.get("source_findings") if "result" in locals() else None,source_checked=actual_search)
    domains=_update_domain_stats(items,actual_search=actual_search)
    if not locals().get("skipped_reason") and not (cache_fresh and not items):
        cache_defaults={"query":query,"searched_at":timezone.now(),"result_count":len(items),"query_family":query_family(profile_id,strategy_id),"query_signature":query_signature(query),"result_payload":items[:settings.DISCOVERY_MAX_RESULTS],"search_findings":result.get("search_findings", ""),"source_findings":result.get("source_findings", []),"source_domains":domains}
        DiscoveryQueryCache.objects.update_or_create(profile_id=profile_id,normalized_query=normalized,defaults=cache_defaults)
    limit=min(qualification_limit or settings.DISCOVERY_MAX_RESULTS,settings.AI_QUALIFICATION_MAX_LEADS_PER_CYCLE); now=timezone.now()
    candidates=list(Lead.objects.filter(status="new",analysis__isnull=True).filter(models.Q(expires_at__isnull=True)|models.Q(expires_at__gt=now)).order_by("-discovered_at","-created_at")[:limit])
    analyzed=qualified=locally_filtered=0; ai_input_tokens=ai_output_tokens=0
    for lead in candidates:
        try:
            local=local_lead_score(lead)
            if not should_ai_qualify(lead): data=ai_skip_analysis(lead,local); locally_filtered+=1
            else:
                data=analyze_lead(lead); ai_input_tokens+=int(data.get("input_tokens",0) or 0); ai_output_tokens+=int(data.get("output_tokens",0) or 0)
            analysis,_=LeadAnalysis.objects.update_or_create(lead=lead,defaults=data); analyzed+=1
            if analysis.relevant and analysis.match_score>=settings.QUALIFICATION_MIN_SCORE:
                lead.status="qualified"; lead.save(update_fields=["status","updated_at"]); qualified+=1
                ActivityLog.objects.create(lead=lead,event_type="lead.auto_qualified",message=f"Lead auto-qualified with score {analysis.match_score}.",metadata={"model":analysis.model,"match_score":analysis.match_score,"threshold":settings.QUALIFICATION_MIN_SCORE})
        except Exception as exc:
            ActivityLog.objects.create(lead=lead,event_type="lead.qualification_failed",message="Lead qualification failed; the lead remains available for retry.",metadata={"error_type":type(exc).__name__,"reason":str(exc)[:500]})
    _refresh_domain_outcomes(items)
    payload=_payload(query,profile_id,source=result.get("source",source),model=result.get("model","unknown"),cached=not actual_search,searched=actual_search,reused=bool(reused_cache),skip_reason=locals().get("skipped_reason"),discovered=len(items),created=created,duplicates=duplicates,invalid=invalid,analyzed=analyzed,qualified=qualified,locally_filtered=locally_filtered,ai_calls=analyzed-locally_filtered,ai_input_tokens=ai_input_tokens,ai_output_tokens=ai_output_tokens,raw_results=raw_results,valid_results=valid_results,unique_results=len(seen),scored_candidates=len(ranked),crawled_candidates=crawled_candidates,strategy_id=strategy_id,query_variant=(selected or {}).get("query_variant","base"),context_size=(selected or {}).get("context_size",settings.DISCOVERY_SEARCH_CONTEXT_SIZE))
    if actual_search:
        _write_search_stat(profile_id,strategy_id,query,result.get("source","web_search"),query_family=query_family(profile_id,strategy_id),query_variant=(selected or {}).get("query_variant","base"),source_domains=domains,context_size=(selected or {}).get("context_size",settings.DISCOVERY_SEARCH_CONTEXT_SIZE),raw_results=raw_results,valid_results=valid_results,unique_results=len(seen),scored_candidates=len(ranked),crawled_candidates=crawled_candidates,newly_created_leads=created,duplicates=duplicates,locally_filtered=locally_filtered,ai_calls=analyzed-locally_filtered,analyzed=analyzed,qualified=qualified)
    ActivityLog.objects.create(event_type="ai.usage",message="Discovery AI usage recorded.",metadata={"operation":"qualification","model":result.get("model","unknown") if 'result' in locals() else "cached","ai_calls":analyzed-locally_filtered,"input_tokens":ai_input_tokens,"output_tokens":ai_output_tokens})
    ActivityLog.objects.create(event_type="discovery.completed",message=f"Discovery cycle completed: {created} new leads, {qualified} qualified.",metadata=payload)
    return payload
