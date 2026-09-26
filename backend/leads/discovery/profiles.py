from datetime import datetime

from django.db.models import Max
from django.utils import timezone

from ..models import DiscoveryQueryCache


DISCOVERY_PROFILES = [
    {"id": "ai-automation", "label": "AI & Automation", "query": "current public freelance opportunities for AI products, AI agents, workflow automation, Python automation and business automation"},
    {"id": "django-fullstack", "label": "Django & Full-Stack", "query": "current public freelance opportunities for Django, Django REST Framework, Python backend, React and full-stack development"},
    {"id": "interactive-web", "label": "React & Three.js", "query": "current public freelance opportunities for React, Three.js, WebGL, interactive websites and 3D web development"},
    {"id": "startup-build", "label": "Startup MVPs", "query": "current public freelance opportunities from startups seeking an MVP, SaaS prototype, AI MVP or full-stack product developer"},
]


def normalize_query(query):
    return " ".join((query or "").lower().split())


def select_profile(ttl_hours, only_if_due=True):
    now = timezone.now()
    stale_before = now - timezone.timedelta(hours=ttl_hours)
    candidates = []

    for profile in DISCOVERY_PROFILES:
        cache = DiscoveryQueryCache.objects.filter(
            profile_id=profile["id"],
            normalized_query=normalize_query(profile["query"]),
        ).first()
        searched_at = cache.searched_at if cache else None
        if only_if_due and searched_at and searched_at > stale_before:
            continue
        candidates.append((searched_at or datetime.min.replace(tzinfo=now.tzinfo), profile))

    if candidates:
        return min(candidates, key=lambda item: item[0])[1]

    # All profiles are fresh; rotate to the least-recently searched profile anyway.
    return min(
        (
            (
                DiscoveryQueryCache.objects.filter(
                    profile_id=profile["id"],
                    normalized_query=normalize_query(profile["query"]),
                ).values_list("searched_at", flat=True).first()
                or datetime.min.replace(tzinfo=now.tzinfo),
                profile,
            )
            for profile in DISCOVERY_PROFILES
        ),
        key=lambda item: item[0],
    )[1]


def public_profiles():
    return DISCOVERY_PROFILES
