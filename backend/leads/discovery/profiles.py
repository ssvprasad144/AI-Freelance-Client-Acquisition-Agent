import hashlib
import math
import re
from datetime import datetime
from urllib.parse import urlparse
from django.conf import settings
from django.db.models import Sum
from django.utils import timezone
from ..models import DiscoveryDomainStat, DiscoveryQueryCache, DiscoverySearchStat

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
QUERY_VARIANTS=[
 ("base","current"),
 ("recent","newly posted recent"),
 ("client-request","client request seeking developer"),
 ("project","project requirement contract opportunity"),
]

def normalize_query(query): return " ".join((query or "").lower().split())

def query_signature(query):
    tokens=sorted(set(re.findall(r"[a-z0-9]{3,}",normalize_query(query))))
    return hashlib.sha256(" ".join(tokens).encode()).hexdigest()[:32]

def query_family(profile_id,strategy_id):
    return f"{profile_id}:{strategy_id}"

def _strategy_map(): return {x["id"]:x for x in STRATEGIES}

def _strategy_query(profile,strategy,variant_id="base"):
    modifier=dict(QUERY_VARIANTS).get(variant_id,"current")
    return f"{profile['query']}. {strategy['suffix']} Emphasize {modifier} opportunities. Return only current opportunities with verifiable public URLs."

def _history(strategy_id,lookback_days=None):
    days=lookback_days or settings.DISCOVERY_LEARNING_LOOKBACK_DAYS
    return DiscoverySearchStat.objects.filter(strategy_id=strategy_id,search_date__gte=timezone.localdate()-timezone.timedelta(days=days))

def _score(strategy_id,lookback_days=None):
    qs=_history(strategy_id,lookback_days); searches=qs.count()
    if not searches: return {"searches":0,"qualified_per_search":0.0,"reply_per_search":0.0,"win_per_search":0.0,"score":0.0}
    t=qs.aggregate(qualified=Sum("qualified"),replied=Sum("replied"),won=Sum("won")); q=(t["qualified"] or 0)/searches; r=(t["replied"] or 0)/searches; w=(t["won"] or 0)/searches
    return {"searches":searches,"qualified_per_search":round(q,3),"reply_per_search":round(r,3),"win_per_search":round(w,3),"score":round(q+r*.35+w*1.5,4)}

def _arm_history(profile_id,strategy_id,lookback_days=None):
    days=lookback_days or settings.DISCOVERY_LEARNING_LOOKBACK_DAYS
    return DiscoverySearchStat.objects.filter(profile_id=profile_id,strategy_id=strategy_id,search_date__gte=timezone.localdate()-timezone.timedelta(days=days))

def _arm_score(profile_id,strategy_id,lookback_days=None,total_searches=None):
    qs=_arm_history(profile_id,strategy_id,lookback_days); searches=qs.count()
    if not searches: return {"profile_id":profile_id,"strategy_id":strategy_id,"searches":0,"qualified_per_search":0.0,"reply_per_search":0.0,"win_per_search":0.0,"reward":0.0,"ucb":float("inf")}
    t=qs.aggregate(qualified=Sum("qualified"),replied=Sum("replied"),won=Sum("won")); q=(t["qualified"] or 0)/searches; r=(t["replied"] or 0)/searches; w=(t["won"] or 0)/searches
    reward=q+r*.35+w*1.5; total=max(total_searches or searches,searches); bonus=math.sqrt((2.0*math.log(max(total,2)))/searches)
    return {"profile_id":profile_id,"strategy_id":strategy_id,"searches":searches,"qualified_per_search":round(q,3),"reply_per_search":round(r,3),"win_per_search":round(w,3),"reward":round(reward,4),"ucb":round(reward+bonus,4)}

def _last_arm_search(profile_id,strategy_id):
    return DiscoverySearchStat.objects.filter(profile_id=profile_id,strategy_id=strategy_id).order_by("-created_at").values_list("created_at",flat=True).first()

def _select_arm(lookback_days=None):
    arms=[_arm_score(p["id"],s["id"],lookback_days) for p in DISCOVERY_PROFILES for s in STRATEGIES]
    under=[a for a in arms if a["searches"]<settings.DISCOVERY_MIN_EXPLORATION_SEARCHES]
    if under: return min(under,key=lambda a:(a["searches"],_last_arm_search(a["profile_id"],a["strategy_id"]) or timezone.make_aware(datetime.min)))
    total=sum(a["searches"] for a in arms)
    arms=[_arm_score(a["profile_id"],a["strategy_id"],lookback_days,total) for a in arms]
    return max(arms,key=lambda a:(a["ucb"],-a["searches"]))

def _variant_score(profile_id,strategy_id,variant_id,lookback_days=None):
    days=lookback_days or settings.DISCOVERY_LEARNING_LOOKBACK_DAYS
    qs=DiscoverySearchStat.objects.filter(profile_id=profile_id,strategy_id=strategy_id,query_variant=variant_id,search_date__gte=timezone.localdate()-timezone.timedelta(days=days))
    searches=qs.count()
    if not searches: return {"variant_id":variant_id,"searches":0,"reward":0.0,"ucb":float("inf")}
    t=qs.aggregate(q=Sum("qualified"),r=Sum("replied"),w=Sum("won")); reward=(t["q"] or 0)/searches+0.35*(t["r"] or 0)/searches+1.5*(t["w"] or 0)/searches
    total=DiscoverySearchStat.objects.filter(search_date__gte=timezone.localdate()-timezone.timedelta(days=days)).count()
    bonus=math.sqrt((2*math.log(max(total,2)))/searches)
    return {"variant_id":variant_id,"searches":searches,"reward":round(reward,4),"ucb":round(reward+bonus,4)}

def select_query_variant(profile_id,strategy_id,lookback_days=None):
    stats=[_variant_score(profile_id,strategy_id,v[0],lookback_days) for v in QUERY_VARIANTS]
    under=[x for x in stats if x["searches"]<settings.DISCOVERY_QUERY_VARIANT_MIN_SEARCHES]
    return (min(under,key=lambda x:x["searches"]) if under else max(stats,key=lambda x:(x["ucb"],-x["searches"])))["variant_id"]

def domain_performance(lookback_days=None):
    return list(DiscoveryDomainStat.objects.order_by("-qualified","-results").values("domain","searches","results","qualified","replied","won","blocked_until")[:100])

def blocked_domains():
    now=timezone.now()
    return list(DiscoveryDomainStat.objects.filter(blocked_until__gt=now).values_list("domain",flat=True))

def domain_exclusions():
    domains=blocked_domains()
    return " ".join(f'-site:{d}' for d in domains[:settings.DISCOVERY_MAX_EXCLUDED_DOMAINS])

def select_context_size(profile_id,strategy_id):
    recent=_arm_score(profile_id,strategy_id)
    if recent["searches"]<settings.DISCOVERY_MIN_EXPLORATION_SEARCHES: return "low"
    return "medium" if recent["qualified_per_search"] < settings.DISCOVERY_LOW_YIELD_THRESHOLD and settings.DISCOVERY_SEARCH_CONTEXT_FALLBACK else "low"

def daily_search_limit(fresh_inventory=0):
    base=settings.DISCOVERY_MAX_SEARCHES_PER_DAY
    target=max(settings.DISCOVERY_TARGET_QUALIFIED_LEADS,1)
    if fresh_inventory >= int(target*.75): return min(base,1)
    if fresh_inventory >= int(target*.4): return min(base,2)
    return base

def preferred_search_window_open():
    if not settings.DISCOVERY_PREFERRED_HOURS_ENABLED: return True
    hour=timezone.localtime().hour
    start,end=settings.DISCOVERY_PREFERRED_HOUR_START,settings.DISCOVERY_PREFERRED_HOUR_END
    return start<=hour<end

def select_strategy(lookback_days=None):
    stats=[(s,_score(s["id"],lookback_days)) for s in STRATEGIES]
    under=[(s,v) for s,v in stats if v["searches"]<settings.DISCOVERY_MIN_EXPLORATION_SEARCHES]
    if under: return min(under,key=lambda x:_last_arm_search("","") or timezone.make_aware(datetime.min))[0]
    return max(stats,key=lambda x:x[1]["score"])[0]

def select_profile(ttl_hours,only_if_due=True,strategy_id=None):
    now=timezone.now(); stale=now-timezone.timedelta(hours=ttl_hours); explicit=strategy_id is not None
    if explicit:
        strategy=_strategy_map()[strategy_id]; arm={"profile_id":DISCOVERY_PROFILES[0]["id"],"strategy_id":strategy_id}
    else:
        arm=_select_arm(); strategy=_strategy_map()[arm["strategy_id"]]
    profiles=[p for p in DISCOVERY_PROFILES if p["id"]==arm["profile_id"]] if not explicit else DISCOVERY_PROFILES
    candidates=[]
    for p in profiles:
        variant=select_query_variant(p["id"],strategy["id"])
        q=_strategy_query(p,strategy,variant)
        cache=DiscoveryQueryCache.objects.filter(profile_id=p["id"],normalized_query=normalize_query(q)).first()
        searched=cache.searched_at if cache else None
        if only_if_due and searched and searched>stale: continue
        candidates.append((searched or datetime.min.replace(tzinfo=now.tzinfo),p,q,variant))
    if not candidates:
        candidates=[(DiscoveryQueryCache.objects.filter(profile_id=p["id"]).order_by("searched_at").values_list("searched_at",flat=True).first() or datetime.min.replace(tzinfo=now.tzinfo),p,_strategy_query(p,strategy,"base"),"base") for p in profiles]
    _,p,q,variant=min(candidates,key=lambda x:x[0])
    return {**p,"strategy_id":strategy["id"],"query":q,"query_variant":variant,"query_family":query_family(p["id"],strategy["id"]),"selection_mode":"adaptive" if explicit else "contextual-bandit","context_size":select_context_size(p["id"],strategy["id"]),"domain_exclusions":domain_exclusions()}

def profile_performance(lookback_days=None):
    return [{"profile":p,"strategies":[{"strategy":s,"performance":_score(s["id"],lookback_days)} for s in STRATEGIES]} for p in DISCOVERY_PROFILES]

def strategy_performance(lookback_days=None): return [{"strategy":s,"performance":_score(s["id"],lookback_days)} for s in STRATEGIES]
def arm_performance(lookback_days=None): return [_arm_score(p["id"],s["id"],lookback_days) for p in DISCOVERY_PROFILES for s in STRATEGIES]
def public_profiles(): return [{**p,"strategies":STRATEGIES} for p in DISCOVERY_PROFILES]

def reusable_cache(query,profile_id=None,ttl_hours=None):
    ttl=ttl_hours or settings.DISCOVERY_QUERY_CACHE_TTL_HOURS
    cutoff=timezone.now()-timezone.timedelta(hours=ttl)
    signature=query_signature(query)
    qs=DiscoveryQueryCache.objects.filter(searched_at__gte=cutoff,query_signature=signature).exclude(result_payload=[])
    if profile_id: qs=qs.exclude(profile_id=profile_id)
    return qs.order_by("-searched_at").first()

def query_similarity(query_a,query_b):
    a=set(re.findall(r"[a-z0-9]{3,}",normalize_query(query_a))); b=set(re.findall(r"[a-z0-9]{3,}",normalize_query(query_b)))
    return len(a&b)/max(len(a|b),1)
