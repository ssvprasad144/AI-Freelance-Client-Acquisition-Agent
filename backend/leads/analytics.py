from django.db.models import Count, Q
from django.utils import timezone
from .models import ActivityLog, Lead, Outreach, Reply

def acquisition_metrics():
    total=Lead.objects.count()
    qualified=Lead.objects.filter(status__in=["qualified","proposal","contacted","replied","won"]).count()
    proposals=Outreach.objects.filter(status__in=["draft","approved","sent"]).count()
    approved=Outreach.objects.filter(status__in=["approved","sent"]).count()
    sent=Outreach.objects.filter(status="sent").count()
    replied=Lead.objects.filter(status__in=["replied","won"]).count()
    won=Lead.objects.filter(status="won").count()
    lost=Lead.objects.filter(status="lost").count()
    def rate(n,d): return round((n/d)*100,2) if d else 0
    source_rows=Lead.objects.values("source").annotate(total=Count("id"),qualified=Count("id",filter=Q(status__in=["qualified","proposal","contacted","replied","won"])),replied=Count("id",filter=Q(status__in=["replied","won"])),won=Count("id",filter=Q(status="won"))).order_by("-total")
    service_rows=Lead.objects.values("lead_type").annotate(total=Count("id"),won=Count("id",filter=Q(status="won")),replied=Count("id",filter=Q(status__in=["replied","won"]))).order_by("-total")
    return {
        "funnel":{"discovered":total,"qualified":qualified,"proposals":proposals,"approved":approved,"sent":sent,"replied":replied,"won":won,"lost":lost},
        "rates":{"qualification_rate":rate(qualified,total),"proposal_rate":rate(proposals,qualified),"approval_rate":rate(approved,proposals),"send_rate":rate(sent,approved),"reply_rate":rate(replied,sent),"win_rate":rate(won,replied)},
        "sources":list(source_rows),
        "lead_types":list(service_rows),
        "generated_at":timezone.now(),
    }
