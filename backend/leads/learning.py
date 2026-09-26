from collections import defaultdict
from django.db.models import Q
from .models import AcquisitionEvent, DiscoverySearchStat, Lead, LearningStat, Meeting, Outreach
WEIGHTS={"qualified":1.0,"proposal":2.0,"sent":3.0,"reply":5.0,"meeting":10.0,"won":25.0,"lost":-5.0}
def lead_reward(lead):
    status=lead.status
    reward=WEIGHTS.get(status,0)
    if lead.replies.exists(): reward=max(reward,WEIGHTS["reply"])
    if lead.meetings.filter(status__in=["requested","scheduled","completed"]).exists(): reward=max(reward,WEIGHTS["meeting"])
    if lead.status=="won": reward=WEIGHTS["won"]
    return reward
def refresh_discovery_outcomes():
    updated=0
    for stat in DiscoverySearchStat.objects.all().iterator():
        leads=Lead.objects.filter(discovery_profile=stat.profile_id,discovery_strategy=stat.strategy_id,discovery_query=stat.query,discovered_at__date=stat.search_date)
        replies=leads.filter(status__in=["replied","won"]).count()
        won=leads.filter(status="won").count()
        if stat.replied != replies or stat.won != won:
            stat.replied=replies; stat.won=won; stat.save(update_fields=["replied","won","updated_at"]); updated+=1
    return updated

def refresh_learning():
    refresh_discovery_outcomes()
    buckets=defaultdict(list)
    for lead in Lead.objects.all():
        keys=[("source",lead.source),("lead_type",lead.lead_type)]
        if lead.discovery_profile: keys.append(("profile",lead.discovery_profile))
        if lead.discovery_strategy: keys.append(("strategy",lead.discovery_strategy))
        if lead.discovery_query: keys.append(("query",lead.discovery_query))
        for key in keys: buckets[key].append(lead)
        for event in lead.acquisition_events.all()[:100]:
            if event.domain: buckets[("domain",event.domain)].append(lead)
    LearningStat.objects.all().delete()
    for (dimension,key),leads in buckets.items():
        unique={lead.id:lead for lead in leads}.values()
        attempts=qualified=proposals=sent=replies=meetings=wins=losses=0
        reward=0.0
        for lead in unique:
            attempts+=1
            qualified+=int(lead.status in {"qualified","proposal","contacted","replied","won"})
            proposals+=int(lead.proposals.exists())
            sent+=int(lead.outreach.filter(status="sent").exists())
            replies+=int(lead.replies.exists())
            meetings+=int(lead.meetings.filter(status__in=["requested","scheduled","completed"]).exists())
            wins+=int(lead.status=="won"); losses+=int(lead.status=="lost"); reward+=lead_reward(lead)
        LearningStat.objects.create(dimension=dimension,key=key,attempts=attempts,qualified=qualified,proposals=proposals,sent=sent,replies=replies,meetings=meetings,wins=wins,losses=losses,reward=round(reward,3))
    return list(LearningStat.objects.values().order_by("-reward","-attempts")[:100])
def log_acquisition_event(lead,event_type,metadata=None):
    return AcquisitionEvent.objects.create(lead=lead,event_type=event_type,source=lead.source,profile_id=lead.discovery_profile,strategy_id=lead.discovery_strategy,query=lead.discovery_query,metadata=metadata or {})
