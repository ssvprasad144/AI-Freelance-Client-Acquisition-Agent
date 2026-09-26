from datetime import datetime

from django.conf import settings
from django.db.models import Sum
from django.utils import timezone

from ..models import DiscoveryQueryCache, DiscoverySearchStat

STRATEGIES = [
    {"id":"marketplace","label":"Freelance marketplaces","suffix":"Focus on publicly indexed freelance marketplace project listings and client requests from sites such as Upwork, Freelancer, PeoplePerHour, Guru and similar marketplaces. Exclude generic job articles and tutorials."},
    {"id":"community","label":"Communities","suffix":"Focus on public community posts where people explicitly request developers, automation, AI, websites or software help, especially Reddit and public forums."},
    {"id":"startup-hiring","label":"Startup hiring","suffix":"Focus on startup, SaaS and company pages publicly seeking freelance, contract, project or MVP developers. Prefer direct company/client pages over aggregators."},
    {"id":"direct-web","label":"Direct web","suffix":"Search the broader public web for current client project requests, agency outsourcing requests, public RFPs and other directly relevant software-development opportunities."},
]

DISCOVERY_PROFILES = [
    {"id":"ai-automation","label":"AI & Automation","query":"current public freelance opportunities for AI products, AI agents, workflow automation, Python automation and business automation"},
    {"id":"django-fullstack","label":"Django & Full-Stack","query":"current public freelance opportunities for Django, Django REST Framework, Python backend, React and full-stack development"},
    {"id":"interactive-web","label":"React & Three.js","query":"current public freelance opportunities for React, Three.js, WebGL, interactive websites and 3D web development"},
    {"id":"startup-build","label":"Startup MVPs","query":"current public freelance opportunities from startups seeking an MVP, SaaS prototype, AI MVP or full-stack product developer"},
]


def normalize_query(query):
    return " ".join((query or "").lower().split())


def _strategy_map(): return {item["id"]: item for item in STRATEGIES}


def _strategy_query(profile, strategy):
    return f"{profile['query']}. {strategy['suffix']} Return only current opportunities with verifiable public URLs."


def _history(strategy_id, lookback_days=None):
    days=lookback_days or settings.DISCOVERY_LEARNING_LOOKBACK_DAYS
    since=timezone.localdate()-timezone.timedelta(days=days)
    return DiscoverySearchStat.objects.filter(strategy_id=strategy_id,search_date__gte=since)


def _score(strategy_id, lookback_days=None):
    qs=_history(strategy_id,lookback_days); searches=qs.count()
    if not searches: return {"searches":0,"qualified_per_search":0.0,"reply_per_search":0.0,"win_per_search":0.0,"score":0.0}
    t=qs.aggregate(qualified=Sum("qualified"),replied=Sum("replied"),won=Sum("won"))
    q=(t["qualified"] or 0)/searches; r=(t["replied"] or 0)/searches; w=(t["won"] or 0)/searches
    score=q+(r*0.35)+(w*1.5)
    return {"searches":searches,"qualified_per_search":round(q,3),"reply_per_search":round(r,3),"win_per_search":round(w,3),"score":round(score,4)}


def select_strategy(lookback_days=None):
    stats=[(strategy,_score(strategy["id"],lookback_days)) for strategy in STRATEGIES]
    minimum=settings.DISCOVERY_MIN_EXPLORATION_SEARCHES
    unexplored=[(s,v) for s,v in stats if v["searches"]<minimum]
    if unexplored:
        return min(unexplored,key=lambda item: next((x.created_at for x in DiscoverySearchStat.objects.filter(strategy_id=item[0]["id"]).order_by("-created_at")[:1]), timezone.make_aware(datetime.min)))[0]
    best=max(v["score"] for _,v in stats)
    return min([s for s,v in stats if v["score"]==best],key=lambda s: s["id"])


def select_profile(ttl_hours, only_if_due=True, strategy_id=None):
    now=timezone.now(); stale_before=now-timezone.timedelta(hours=ttl_hours); candidates=[]
    for profile in DISCOVERY_PROFILES:
        strategy=strategy_id or select_strategy()
        query=_strategy_query(profile,_strategy_map()[strategy])
        cache=DiscoveryQueryCache.objects.filter(profile_id=profile["id"],normalized_query=normalize_query(query)).first()
        searched_at=cache.searched_at if cache else None
        if only_if_due and searched_at and searched_at>stale_before: continue
        candidates.append((searched_at or datetime.min.replace(tzinfo=now.tzinfo),profile,strategy,query))
    if not candidates:
        strategy=strategy_id or select_strategy(); profile=min(DISCOVERY_PROFILES,key=lambda p:p["id"]); return {**profile,"strategy_id":strategy,"query":_strategy_query(profile,_strategy_map()[strategy])}
    _,profile,strategy,query=min(candidates,key=lambda item:item[0])
    return {**profile,"strategy_id":strategy,"query":query}


def profile_performance(lookback_days=None):
    return [{"profile":p,"strategies":[{"strategy":s,"performance":_score(s["id"],lookback_days)} for s in STRATEGIES]} for p in DISCOVERY_PROFILES]


def public_profiles(): return [{**profile,"strategies":STRATEGIES} for profile in DISCOVERY_PROFILES]
