from datetime import datetime
from django.conf import settings
from django.db.models import Sum
from django.utils import timezone
from ..models import DiscoveryQueryCache, DiscoverySearchStat

STRATEGIES=[
 {"id":"marketplace","label":"Freelance marketplaces","suffix":"Focus on publicly indexed freelance marketplace project listings and client requests from sites such as Upwork, Freelancer, PeoplePerHour, Guru and similar marketplaces. Exclude generic job articles and tutorials."},
 {"id":"community","label":"Communities","suffix":"Focus on public community posts where people explicitly request developers, automation, AI, websites or software help, especially Reddit and public forums."},
 {"id":"startup-hiring","label":"Startup hiring","suffix":"Focus on startup, SaaS and company pages publicly seeking freelance, contract, project or MVP developers. Prefer direct company/client pages over aggregators."},
 {"id":"direct-web","label":"Direct web","suffix":"Search the broader public web for current client project requests, agency outsourcing requests, public RFPs and other directly relevant software-development opportunities."},
]
DISCOVERY_PROFILES=[
 {"id":"ai-automation","label":"AI & Automation","query":"current public freelance opportunities for AI products, AI agents, workflow automation, Python automation and business automation"},
 {"id":"django-fullstack","label":"Django & Full-Stack","query":"current public freelance opportunities for Django, Django REST Framework, Python backend, React and full-stack development"},
 {"id":"interactive-web","label":"React & Three.js","query":"current public freelance opportunities for React, Three.js, WebGL, interactive websites and 3D web development"},
 {"id":"startup-build","label":"Startup MVPs","query":"current public freelance opportunities from startups seeking an MVP, SaaS prototype, AI MVP or full-stack product developer"},
]
def normalize_query(query): return " ".join((query or "").lower().split())
def _strategy_map(): return {x["id"]:x for x in STRATEGIES}
def _strategy_query(profile,strategy): return f"{profile['query']}. {strategy['suffix']} Return only current opportunities with verifiable public URLs."
def _history(strategy_id,lookback_days=None):
    days=lookback_days or settings.DISCOVERY_LEARNING_LOOKBACK_DAYS
    return DiscoverySearchStat.objects.filter(strategy_id=strategy_id,search_date__gte=timezone.localdate()-timezone.timedelta(days=days))
def _score(strategy_id,lookback_days=None):
    qs=_history(strategy_id,lookback_days); searches=qs.count()
    if not searches: return {"searches":0,"qualified_per_search":0.0,"reply_per_search":0.0,"win_per_search":0.0,"score":0.0}
    t=qs.aggregate(qualified=Sum("qualified"),replied=Sum("replied"),won=Sum("won")); q=(t["qualified"] or 0)/searches; r=(t["replied"] or 0)/searches; w=(t["won"] or 0)/searches
    return {"searches":searches,"qualified_per_search":round(q,3),"reply_per_search":round(r,3),"win_per_search":round(w,3),"score":round(q+r*.35+w*1.5,4)}
def _last_search(strategy_id): return DiscoverySearchStat.objects.filter(strategy_id=strategy_id).order_by("-created_at").values_list("created_at",flat=True).first()
def select_strategy(lookback_days=None):
    stats=[(s,_score(s["id"],lookback_days)) for s in STRATEGIES]
    under=[(s,v) for s,v in stats if v["searches"]<settings.DISCOVERY_MIN_EXPLORATION_SEARCHES]
    if under: return min(under,key=lambda x:_last_search(x[0]["id"]) or timezone.make_aware(datetime.min))[0]
    best=max(v["score"] for _,v in stats); return min([s for s,v in stats if v["score"]==best],key=lambda s:_last_search(s["id"]) or timezone.make_aware(datetime.min))
def select_profile(ttl_hours,only_if_due=True,strategy_id=None):
    now=timezone.now(); stale=now-timezone.timedelta(hours=ttl_hours); strategy_id=strategy_id or select_strategy(); strategy=_strategy_map()[strategy_id]; eligible=[]
    for p in DISCOVERY_PROFILES:
        q=_strategy_query(p,strategy); cache=DiscoveryQueryCache.objects.filter(profile_id=p["id"],normalized_query=normalize_query(q)).first(); searched=cache.searched_at if cache else None
        if only_if_due and searched and searched>stale: continue
        eligible.append((searched or datetime.min.replace(tzinfo=now.tzinfo),p,q))
    if not eligible:
        candidates=[(DiscoveryQueryCache.objects.filter(profile_id=p["id"],normalized_query=normalize_query(_strategy_query(p,strategy))).values_list("searched_at",flat=True).first() or datetime.min.replace(tzinfo=now.tzinfo),p,_strategy_query(p,strategy)) for p in DISCOVERY_PROFILES]
        _,p,q=min(candidates,key=lambda x:x[0])
    else:
        _,p,q=min(eligible,key=lambda x:x[0])
    return {**p,"strategy_id":strategy_id,"query":q}
def profile_performance(lookback_days=None): return [{"profile":p,"strategies":[{"strategy":s,"performance":_score(s["id"],lookback_days)} for s in STRATEGIES]} for p in DISCOVERY_PROFILES]
def strategy_performance(lookback_days=None): return [{"strategy":s,"performance":_score(s["id"],lookback_days)} for s in STRATEGIES]
def public_profiles(): return [{**p,"strategies":STRATEGIES} for p in DISCOVERY_PROFILES]
