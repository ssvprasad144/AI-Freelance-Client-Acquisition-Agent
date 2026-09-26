from django.db.models import Count,Q,Sum
from django.utils import timezone
from .models import DiscoveryDomainStat,DiscoverySearchStat,Lead,Outreach,Meeting,Client,AcquisitionEvent,LearningStat
from .discovery.profiles import arm_performance,domain_performance

def _rate(n,d): return round((n/d)*100,2) if d else 0

def _rows(qs,group):
    return list(qs.values(group).annotate(
        opportunities=Count("id",distinct=True),
        qualified=Count("id",distinct=True,filter=Q(status__in=["qualified","proposal","contacted","replied","won"])),
        proposals=Count("id",distinct=True,filter=Q(status__in=["proposal","contacted","replied","won"])),
        contacted=Count("id",distinct=True,filter=Q(status__in=["contacted","replied","won"])),
        replies=Count("id",distinct=True,filter=Q(status__in=["replied","won"])),
        meetings=Count("meetings",distinct=True,filter=Q(meetings__status__in=["requested","scheduled","completed"])),
        won=Count("id",distinct=True,filter=Q(status="won")),
        lost=Count("id",distinct=True,filter=Q(status="lost")),
    ).order_by("-opportunities")[:50])

def acquisition_metrics():
    total=Lead.objects.count()
    qualified=Lead.objects.filter(status__in=["qualified","proposal","contacted","replied","won"]).count()
    proposals=Outreach.objects.filter(status__in=["draft","approved","sent"]).count()
    approved=Outreach.objects.filter(status__in=["approved","sent"]).count()
    sent=Outreach.objects.filter(status="sent").count()
    replied=Lead.objects.filter(status__in=["replied","won"]).count()
    won=Lead.objects.filter(status="won").count()
    lost=Lead.objects.filter(status="lost").count()
    meetings_requested=Meeting.objects.filter(status="requested").count()
    meetings_scheduled=Meeting.objects.filter(status="scheduled").count()
    meetings_completed=Meeting.objects.filter(status="completed").count()
    clients=Client.objects.count()
    active_clients=Client.objects.filter(status__in=["active","won"]).count()
    source_rows=_rows(Lead.objects.all(),"source")
    type_rows=_rows(Lead.objects.all(),"lead_type")
    profile_rows=_rows(Lead.objects.exclude(discovery_profile=""),"discovery_profile")
    strategy_rows=_rows(Lead.objects.exclude(discovery_strategy=""),"discovery_strategy")
    domain_rows=list(DiscoveryDomainStat.objects.values("domain","searches","results","qualified","replied","won").order_by("-qualified","-results")[:50])
    learning_rows=list(LearningStat.objects.values().order_by("-reward","-attempts")[:50])
    funnel=[
        {"stage":"discovered","count":total},
        {"stage":"qualified","count":qualified},
        {"stage":"proposal_generated","count":proposals},
        {"stage":"approved","count":approved},
        {"stage":"sent","count":sent},
        {"stage":"replied","count":replied},
        {"stage":"meeting_requested","count":meetings_requested},
        {"stage":"meeting_scheduled","count":meetings_scheduled},
        {"stage":"meeting_completed","count":meetings_completed},
        {"stage":"won","count":won},
        {"stage":"lost","count":lost},
    ]
    return {
        "funnel":{"discovered":total,"qualified":qualified,"proposals":proposals,"approved":approved,"sent":sent,"replied":replied,"meeting_requested":meetings_requested,"meeting_scheduled":meetings_scheduled,"meeting_completed":meetings_completed,"won":won,"lost":lost},
        "rates":{
            "qualification_rate":_rate(qualified,total),"proposal_rate":_rate(proposals,qualified),"approval_rate":_rate(approved,proposals),
            "send_rate":_rate(sent,approved),"reply_rate":_rate(replied,sent),"meeting_request_rate":_rate(meetings_requested,replied),
            "meeting_completion_rate":_rate(meetings_completed,meetings_scheduled),"win_rate":_rate(won,meetings_completed or replied),
        },
        "clients":{"total":clients,"active_or_won":active_clients,"new_prospects":Client.objects.filter(status="prospect").count()},
        "meetings":{"requested":meetings_requested,"scheduled":meetings_scheduled,"completed":meetings_completed,"cancelled":Meeting.objects.filter(status="cancelled").count(),"no_show":Meeting.objects.filter(status="no_show").count()},
        "funnel_series":funnel,"sources":source_rows,"lead_types":type_rows,"profiles":profile_rows,"strategies":strategy_rows,
        "domains":domain_rows,"learning":learning_rows,"search_learning":_search_learning(),"arm_learning":arm_performance(),"domain_learning":domain_performance(),"generated_at":timezone.now()
    }

def _search_learning():
    rows=DiscoverySearchStat.objects.values("profile_id","strategy_id").annotate(searches=Count("id"),created=Sum("newly_created_leads"),qualified=Sum("qualified"),replied=Sum("replied"),won=Sum("won"))
    return [{**r,"qualified_per_search":round((r["qualified"] or 0)/(r["searches"] or 1),3),"reply_per_search":round((r["replied"] or 0)/(r["searches"] or 1),3),"win_per_search":round((r["won"] or 0)/(r["searches"] or 1),3)} for r in rows.order_by("-qualified")[:50]]
