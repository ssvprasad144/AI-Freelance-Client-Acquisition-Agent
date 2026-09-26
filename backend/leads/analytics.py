from django.db.models import Count,Q,Sum
from django.utils import timezone
from .models import ActivityLog,DiscoverySearchStat,Lead,Outreach,Reply

def acquisition_metrics():
    total=Lead.objects.count(); qualified=Lead.objects.filter(status__in=["qualified","proposal","contacted","replied","won"]).count(); proposals=Outreach.objects.filter(status__in=["draft","approved","sent"]).count(); approved=Outreach.objects.filter(status__in=["approved","sent"]).count(); sent=Outreach.objects.filter(status="sent").count(); replied=Lead.objects.filter(status__in=["replied","won"]).count(); won=Lead.objects.filter(status="won").count(); lost=Lead.objects.filter(status="lost").count()
    def rate(n,d): return round((n/d)*100,2) if d else 0
    source_rows=Lead.objects.values("source").annotate(total=Count("id"),qualified=Count("id",filter=Q(status__in=["qualified","proposal","contacted","replied","won"])),replied=Count("id",filter=Q(status__in=["replied","won"])),won=Count("id",filter=Q(status="won"))).order_by("-total")
    service_rows=Lead.objects.values("lead_type").annotate(total=Count("id"),won=Count("id",filter=Q(status="won")),replied=Count("id",filter=Q(status__in=["replied","won"]))).order_by("-total")
    stats=DiscoverySearchStat.objects.values("profile_id").annotate(searches=Count("id"),raw_results=Sum("raw_results"),unique_results=Sum("unique_results"),created=Sum("newly_created_leads"),qualified=Sum("qualified"),ai_calls=Sum("ai_calls"),replied=Sum("replied"),won=Sum("won")).order_by("-qualified")
    search_learning=[]
    for row in stats:
        searches=row["searches"] or 0
        search_learning.append({**row,"qualified_per_search":round((row["qualified"] or 0)/searches,2) if searches else 0,"created_per_search":round((row["created"] or 0)/searches,2) if searches else 0,"qualification_from_created_pct":rate(row["qualified"] or 0,row["created"] or 0)})
    return {"funnel":{"discovered":total,"qualified":qualified,"proposals":proposals,"approved":approved,"sent":sent,"replied":replied,"won":won,"lost":lost},"rates":{"qualification_rate":rate(qualified,total),"proposal_rate":rate(proposals,qualified),"approval_rate":rate(approved,proposals),"send_rate":rate(sent,approved),"reply_rate":rate(replied,sent),"win_rate":rate(won,replied)},"sources":list(source_rows),"lead_types":list(service_rows),"search_learning":search_learning,"generated_at":timezone.now()}
