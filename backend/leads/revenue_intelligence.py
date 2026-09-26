from django.db.models import Sum,Count,Q
from django.utils import timezone
from .models import RevenueRecord, Lead, AcquisitionEvent, LearningStat

def expected_value(record):
    return round(float(record.quoted_value or record.estimated_value or 0)*float(record.probability or 0)/100,2)

def upsert_revenue(lead,data):
    estimated=float(data.get("estimated_value",0) or 0); quoted=float(data.get("quoted_value",0) or 0); won=float(data.get("won_value",0) or 0)
    probability=float(data.get("probability",100 if lead.status=="won" else 25) or 0)
    obj,_=RevenueRecord.objects.update_or_create(lead=lead,defaults={
        "estimated_value":estimated,"quoted_value":quoted,"won_value":won,"currency":str(data.get("currency") or getattr(__import__("django.conf",fromlist=["settings"]).settings,"REVENUE_DEFAULT_CURRENCY","USD")).upper()[:3],
        "probability":max(0,min(100,probability)),"search_cost":float(data.get("search_cost",0) or 0),
        "ai_cost":float(data.get("ai_cost",0) or 0),"crawler_cost":float(data.get("crawler_cost",0) or 0),
        "outreach_cost":float(data.get("outreach_cost",0) or 0),"updated_at":timezone.now(),
    })
    obj.expected_value=expected_value(obj); obj.save(update_fields=["expected_value","updated_at"])
    return obj

def revenue_metrics():
    qs=RevenueRecord.objects.all()
    total=float(qs.aggregate(v=Sum("won_value"))["v"] or 0)
    expected=float(qs.aggregate(v=Sum("expected_value"))["v"] or 0)
    costs=qs.aggregate(search=Sum("search_cost"),ai=Sum("ai_cost"),crawler=Sum("crawler_cost"),outreach=Sum("outreach_cost"))
    cost_total=sum(float(v or 0) for v in costs.values())
    roi=round((total-cost_total)/cost_total*100,2) if cost_total else 0
    by_source=list(qs.values("lead__source").annotate(revenue=Sum("won_value"),expected=Sum("expected_value"),leads=Count("id")).order_by("-revenue"))
    by_strategy=list(qs.values("lead__discovery_strategy").annotate(revenue=Sum("won_value"),expected=Sum("expected_value"),leads=Count("id")).order_by("-revenue"))
    return {"revenue":round(total,2),"expected_revenue":round(expected,2),"acquisition_cost":round(cost_total,2),"roi_percent":roi,"costs":{k:round(float(v or 0),2) for k,v in costs.items()},"by_source":by_source,"by_strategy":by_strategy,"pipeline":{"leads":qs.filter(lead__status__in=["qualified","proposal","contacted","replied"]).count(),"meetings":qs.filter(lead__meetings__status__in=["requested","scheduled"],).count(),"won":qs.filter(lead__status="won").count()}}

def refresh_revenue_learning():
    metrics=revenue_metrics()
    for stat in LearningStat.objects.all():
        revenue=RevenueRecord.objects.filter(lead__source=stat.key if stat.dimension=="source" else None).aggregate(v=Sum("won_value"))["v"] if stat.dimension=="source" else 0
        if revenue:
            stat.reward=float(stat.reward)+float(revenue); stat.save(update_fields=["reward","updated_at"])
    return metrics

def optimization_report():
    rows=[]
    for stat in LearningStat.objects.order_by("-reward","-attempts")[:50]:
        conversion=round(stat.wins/max(stat.attempts,1)*100,2)
        rows.append({"dimension":stat.dimension,"key":stat.key,"attempts":stat.attempts,"wins":stat.wins,"reward":round(stat.reward,2),"win_rate":conversion})
    return rows
