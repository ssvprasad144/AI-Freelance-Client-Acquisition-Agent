from datetime import datetime

from django.db.models import Sum
from django.conf import settings
from django.utils import timezone

from ..models import DiscoveryQueryCache, DiscoverySearchStat

DISCOVERY_PROFILES = [
    {"id": "ai-automation", "label": "AI & Automation", "query": "current public freelance opportunities for AI products, AI agents, workflow automation, Python automation and business automation"},
    {"id": "django-fullstack", "label": "Django & Full-Stack", "query": "current public freelance opportunities for Django, Django REST Framework, Python backend, React and full-stack development"},
    {"id": "interactive-web", "label": "React & Three.js", "query": "current public freelance opportunities for React, Three.js, WebGL, interactive websites and 3D web development"},
    {"id": "startup-build", "label": "Startup MVPs", "query": "current public freelance opportunities from startups seeking an MVP, SaaS prototype, AI MVP or full-stack product developer"},
]


def normalize_query(query):
    return " ".join((query or "").lower().split())


def _profiles():
    return {profile["id"]: profile for profile in DISCOVERY_PROFILES}


def _profile_history(profile_id, lookback_days=30):
    since = timezone.localdate() - timezone.timedelta(days=lookback_days)
    return DiscoverySearchStat.objects.filter(profile_id=profile_id, search_date__gte=since)


def _score(profile_id, lookback_days=None):
    qs = _profile_history(profile_id, lookback_days or settings.DISCOVERY_LEARNING_LOOKBACK_DAYS)
    searches = qs.count()
    if not searches:
        return {"searches": 0, "qualified_per_search": 0.0, "created_per_search": 0.0, "reply_per_search": 0.0, "score": 0.0}
    totals = qs.aggregate(qualified=Sum("qualified"), created=Sum("newly_created_leads"), replied=Sum("replied"), won=Sum("won"))
    qualified = totals["qualified"] or 0
    created = totals["created"] or 0
    replied = totals["replied"] or 0
    won = totals["won"] or 0
    # Prioritize qualification efficiency. Reply/win data are included only after they exist.
    qps = qualified / searches
    cps = created / searches
    rps = replied / searches
    wps = won / searches
    score = (qps * 1.0) + (rps * 0.35) + (wps * 1.5)
    return {"searches": searches, "qualified_per_search": round(qps, 3), "created_per_search": round(cps, 3), "reply_per_search": round(rps, 3), "win_per_search": round(wps, 3), "score": round(score, 4)}


def select_profile(ttl_hours, only_if_due=True):
    now = timezone.now()
    stale_before = now - timezone.timedelta(hours=ttl_hours)
    profiles = _profiles()
    candidates = []
    for profile in DISCOVERY_PROFILES:
        cache = DiscoveryQueryCache.objects.filter(profile_id=profile["id"], normalized_query=normalize_query(profile["query"])).first()
        searched_at = cache.searched_at if cache else None
        if only_if_due and searched_at and searched_at > stale_before:
            continue
        candidates.append((searched_at or datetime.min.replace(tzinfo=now.tzinfo), profile))
    eligible = [profile for _, profile in candidates]
    if not eligible:
        eligible = DISCOVERY_PROFILES

    # Exploration floor: profiles with fewer than N observed searches are sampled first.
    minimum_exploration = settings.DISCOVERY_MIN_EXPLORATION_SEARCHES
    observed = [(profile, _score(profile["id"])) for profile in eligible]
    under_sampled = [item for item in observed if item[1]["searches"] < minimum_exploration]
    if under_sampled:
        return min(
            under_sampled,
            key=lambda item: DiscoveryQueryCache.objects.filter(profile_id=item[0]["id"], normalized_query=normalize_query(item[0]["query"])).values_list("searched_at", flat=True).first() or datetime.min.replace(tzinfo=now.tzinfo),
        )[0]

    # Exploit: choose the best measured efficiency; tie-break toward least recently searched.
    best_score = max(item[1]["score"] for item in observed)
    best = [item[0] for item in observed if item[1]["score"] == best_score]
    return min(
        best,
        key=lambda profile: DiscoveryQueryCache.objects.filter(profile_id=profile["id"], normalized_query=normalize_query(profile["query"])).values_list("searched_at", flat=True).first() or datetime.min.replace(tzinfo=now.tzinfo),
    )


def profile_performance(lookback_days=None):
    days = lookback_days or settings.DISCOVERY_LEARNING_LOOKBACK_DAYS
    return [{"profile": profile, "performance": _score(profile["id"], days)} for profile in DISCOVERY_PROFILES]


def public_profiles():
    return DISCOVERY_PROFILES
