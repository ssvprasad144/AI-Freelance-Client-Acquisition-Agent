import json
from urllib.parse import urlparse
from django.conf import settings
from .models import RevenueRecord, AcquisitionEvent, LearningStat, DiscoverySearchStat, ActivityLog, Outreach

def fx_rates():
    rates={str(getattr(settings,"REVENUE_DEFAULT_CURRENCY","USD")).upper():1.0}
    raw=getattr(settings,"REVENUE_FX_RATES","")
    if raw:
        try: rates.update({str(k).upper():float(v) for k,v in json.loads(raw).items() if float(v)>0})
        except (ValueError,TypeError,json.JSONDecodeError): pass
    return rates

def to_reporting(value,currency):
    return float(value or 0)*fx_rates().get(str(currency or settings.REVENUE_DEFAULT_CURRENCY).upper(),1.0)

def expected_value(record):
    base=record.won_value if float(record.won_value or 0)>0 else (record.quoted_value or record.estimated_value or 0)
    return round(float(base)*float(record.probability or 0)/100,2)

def attribution_for(lead):
    domain=urlparse(lead.source_url or "").netloc.lower().removeprefix("www.")
    stat=DiscoverySearchStat.objects.filter(profile_id=lead.discovery_profile,strategy_id=lead.discovery_strategy,query=lead.discovery_query).order_by("-created_at").first()
    channel=Outreach.objects.filter(lead=lead).order_by("-created_at").values_list("medium",flat=True).first() or ""
    plan=lead.outreach_plans.order_by("-updated_at").first()
    return {"source":lead.source,"profile_id":lead.discovery_profile,"strategy_id":lead.discovery_strategy,"domain":domain,"query_family":stat.query_family if stat else "","channel":channel,"message_variant":plan.variant if plan else ""}

def automatic_costs(lead):
    search=DiscoverySearchStat.objects.filter(profile_id=lead.discovery_profile,strategy_id=lead.discovery_strategy,query=lead.discovery_query).count()*float(getattr(settings,"DISCOVERY_SEARCH_UNIT_COST",0))
    crawl=AcquisitionEvent.objects.filter(lead=lead,event_type__icontains="crawl").count()*float(getattr(settings,"CRAWLER_UNIT_COST",0))
    ai=0.0
    for item in ActivityLog.objects.filter(lead=lead,event_type="ai.usage"):
        meta=item.metadata or {}; ai+=float(meta.get("input_tokens",0) or 0)/1000*float(getattr(settings,"AI_INPUT_COST_PER_1K",0)); ai+=float(meta.get("output_tokens",0) or 0)/1000*float(getattr(settings,"AI_OUTPUT_COST_PER_1K",0))
    outreach=Outreach.objects.filter(lead=lead,status__in=["sent","submitted"]).count()*float(getattr(settings,"OUTREACH_UNIT_COST",0))
    return {"search_cost":search,"crawler_cost":crawl,"ai_cost":ai,"outreach_cost":outreach}

def upsert_revenue(lead,data):
    attr=attribution_for(lead); auto=automatic_costs(lead)
    currency=str(data.get("currency") or getattr(settings,"REVENUE_DEFAULT_CURRENCY","USD")).upper()[:3]
    obj,_=RevenueRecord.objects.update_or_create(lead=lead,defaults={
        "estimated_value":float(data.get("estimated_value",0) or 0),"quoted_value":float(data.get("quoted_value",0) or 0),"won_value":float(data.get("won_value",0) or 0),
        "currency":currency,"probability":max(0,min(100,float(data.get("probability",100 if lead.status=="won" else 25) or 0))),
        "search_cost":float(data.get("search_cost",auto["search_cost"]) or 0),"ai_cost":float(data.get("ai_cost",auto["ai_cost"]) or 0),
        "crawler_cost":float(data.get("crawler_cost",auto["crawler_cost"]) or 0),"outreach_cost":float(data.get("outreach_cost",auto["outreach_cost"]) or 0),**attr})
    obj.expected_value=expected_value(obj); obj.save(update_fields=["expected_value","updated_at"]); return obj

def revenue_metrics():
    records=list(RevenueRecord.objects.select_related("lead").all()); reporting=settings.REVENUE_DEFAULT_CURRENCY
    total=sum(to_reporting(r.won_value,r.currency) for r in records); expected=sum(to_reporting(r.expected_value,r.currency) for r in records)
    cost_fields=["search_cost","ai_cost","crawler_cost","outreach_cost"]
    costs={k:sum(to_reporting(getattr(r,k),r.currency) for r in records) for k in cost_fields}; total_cost=sum(costs.values())
    def grouped(field):
        buckets={}
        for r in records:
            key=getattr(r,field) or "unspecified"; b=buckets.setdefault(key,{"key":key,"leads":0,"revenue":0.0,"expected":0.0}); b["leads"]+=1; b["revenue"]+=to_reporting(r.won_value,r.currency); b["expected"]+=to_reporting(r.expected_value,r.currency)
        return sorted(buckets.values(),key=lambda x:x["revenue"],reverse=True)[:50]
    pipeline=[r for r in records if r.lead.status in {"qualified","proposal","contacted","replied"}]
    return {"currency":reporting,"revenue":round(total,2),"expected_revenue":round(expected,2),"acquisition_cost":round(total_cost,4),"roi_percent":round((total-total_cost)/total_cost*100,2) if total_cost else 0,
      "costs":{"search":round(costs["search_cost"],4),"ai":round(costs["ai_cost"],4),"crawler":round(costs["crawler_cost"],4),"outreach":round(costs["outreach_cost"],4)},
      "by_source":grouped("source"),"by_profile":grouped("profile_id"),"by_strategy":grouped("strategy_id"),"by_domain":grouped("domain"),"by_query_family":grouped("query_family"),"by_channel":grouped("channel"),"by_variant":grouped("message_variant"),
      "pipeline":{"leads":len(pipeline),"meetings":sum(r.lead.meetings.filter(status__in=["requested","scheduled"]).count() for r in pipeline),"won":sum(r.lead.status=="won" for r in records)}}

def refresh_revenue_learning():
    metrics=revenue_metrics()
    for stat in LearningStat.objects.all():
        if stat.dimension in {"source","profile","strategy","domain"}:
            field={"source":"source","profile":"profile_id","strategy":"strategy_id","domain":"domain"}[stat.dimension]
            stat.reward=sum(to_reporting(r.won_value,r.currency) for r in RevenueRecord.objects.filter(**{field:stat.key}))
        elif stat.dimension=="query":
            stat.reward=sum(to_reporting(r.won_value,r.currency) for r in RevenueRecord.objects.filter(lead__discovery_query=stat.key))
        stat.save(update_fields=["reward","updated_at"])
    return metrics

def optimization_report():
    return [{"dimension":s.dimension,"key":s.key,"attempts":s.attempts,"qualified":s.qualified,"proposals":s.proposals,"sent":s.sent,"replies":s.replies,"meetings":s.meetings,"wins":s.wins,"losses":s.losses,"reward":round(s.reward,2),"win_rate":round(s.wins/max(s.attempts,1)*100,2)} for s in LearningStat.objects.order_by("-reward","-attempts")[:100]]
