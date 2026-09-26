from datetime import datetime

from django.utils import timezone

from ..models import DiscoveryQueryCache

DISCOVERY_PROFILES=[
    {"id":"ai-automation","label":"AI & Automation","query":"current public freelance opportunities for AI products, AI agents, workflow automation, Python automation and business automation"},
    {"id":"django-fullstack","label":"Django & Full-Stack","query":"current public freelance opportunities for Django, Django REST Framework, Python backend, React and full-stack development"},
    {"id":"interactive-web","label":"React & Three.js","query":"current public freelance opportunities for React, Three.js, WebGL, interactive websites and 3D web development"},
    {"id":"startup-build","label":"Startup MVPs","query":"current public freelance opportunities from startups seeking an MVP, SaaS prototype, AI MVP or full-stack product developer"},
]

def normalize_query(query):
    return " ".join((query or "").lower().split())

def select_profile(ttl_hours):
    now=timezone.now()
    stale_before=now-timezone.timedelta(hours=ttl_hours)
    for profile in DISCOVERY_PROFILES:
        cache=DiscoveryQueryCache.objects.filter(profile_id=profile["id"],normalized_query=normalize_query(profile["query"])).first()
        if not cache or not cache.searched_at or cache.searched_at <= stale_before:
            return profile
    candidates=[]
    for profile in DISCOVERY_PROFILES:
        searched=DiscoveryQueryCache.objects.filter(profile_id=profile["id"],normalized_query=normalize_query(profile["query"])).values_list("searched_at",flat=True).first()
        candidates.append((searched or datetime.min.replace(tzinfo=now.tzinfo),profile))
    return min(candidates,key=lambda item:item[0])[1]

def public_profiles():
    return DISCOVERY_PROFILES
