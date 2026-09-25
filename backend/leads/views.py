from django.conf import settings
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.response import Response
from .ai_service import analyze_lead, generate_proposal
from .models import ActivityLog, Lead, LeadAnalysis, Outreach
from .serializers import ActivityLogSerializer, LeadSerializer
from .discovery.service import DiscoveryService
from .discovery.mock_provider import DiscoveryError
from .discovery.live_provider import LiveDiscoveryError

def health(request): return JsonResponse({"status":"ok","service":"ai-freelance-client-acquisition-agent","discovery":"web_search"})

def _store(items):
    created=duplicates=invalid=0
    with transaction.atomic():
        for item in items:
            if not item.get("title") or not item.get("description") or not item.get("source_url"): invalid+=1; continue
            source=item.get("source") or "web_search"; url=item.get("source_url")
            if Lead.objects.filter(source=source,source_url=url).exists(): duplicates+=1; continue
            if Lead.objects.filter(source=source,title=item.get("title",""),company=item.get("company","" )).exists(): duplicates+=1; continue
            Lead.objects.create(title=item["title"],company=item.get("company",""),description=item["description"],source=source,source_url=url,lead_type=item.get("lead_type","freelance"),budget_text=item.get("budget_text",""),technologies=item.get("technologies") or [],contact_info=item.get("contact_info") or {},discovered_at=timezone.now()); created+=1
    return created,duplicates,invalid

@api_view(["POST"])
def qualify_new_leads(request):
    limit = min(max(int(request.data.get("limit", 20)), 1), 50)
    leads = list(Lead.objects.filter(status="new").order_by("-discovered_at", "-created_at")[:limit])
    qualified = 0
    analyzed = 0
    for lead in leads:
        data = analyze_lead(lead)
        analysis, _ = LeadAnalysis.objects.update_or_create(lead=lead, defaults=data)
        analyzed += 1
        if analysis.relevant:
            lead.status = "qualified"
            lead.save(update_fields=["status", "updated_at"])
            qualified += 1
            ActivityLog.objects.create(
                lead=lead,
                event_type="lead.auto_qualified",
                message=f"Lead auto-qualified with score {analysis.match_score}.",
                metadata={"model": analysis.model, "match_score": analysis.match_score},
            )
    return Response({
        "status": "success",
        "analyzed": analyzed,
        "qualified": qualified,
        "remaining_new": Lead.objects.filter(status="new").count(),
    })


@api_view(["POST"])
def run_discovery(request):
    query=str(request.data.get("query") or settings.DEFAULT_DISCOVERY_QUERY).strip(); source=str(request.data.get("source") or "live").lower()
    try: result=DiscoveryService().discover(query,source)
    except (LiveDiscoveryError,DiscoveryError) as exc: return Response({"status":"error","detail":str(exc)},status=status.HTTP_502_BAD_GATEWAY)
    items=result.get("leads",[]); created,duplicates,invalid=_store(items)
    ActivityLog.objects.create(event_type="discovery.completed",message=f"Discovery completed from {result.get('source',source)}.",metadata={"query":query,"source":result.get("source",source),"discovered":len(items),"created":created,"duplicates":duplicates,"invalid":invalid,"model":result.get("model","unknown")})
    return Response({"status":"success","source":result.get("source",source),"query":query,"discovered":len(items),"created":created,"duplicates":duplicates,"invalid":invalid})

class LeadViewSet(viewsets.ModelViewSet):
    queryset=Lead.objects.all().prefetch_related("analysis"); serializer_class=LeadSerializer
    @action(detail=True,methods=["post"])
    def analyze(self,request,pk=None):
        lead=self.get_object(); data=analyze_lead(lead); analysis,_=LeadAnalysis.objects.update_or_create(lead=lead,defaults=data)
        if analysis.relevant and lead.status=="new": lead.status="qualified"; lead.save(update_fields=["status","updated_at"])
        ActivityLog.objects.create(lead=lead,event_type="lead.analyzed",message=f"Lead analyzed with score {analysis.match_score}.",metadata={"model":analysis.model,"match_score":analysis.match_score})
        return Response(LeadSerializer(lead).data)
    @action(detail=True,methods=["post"])
    def proposal(self,request,pk=None):
        lead=self.get_object(); analysis=getattr(lead,"analysis",None)
        if not analysis:return Response({"detail":"Analyze the lead first."},status=status.HTTP_400_BAD_REQUEST)
        message=generate_proposal(lead,analysis); outreach=Outreach.objects.create(lead=lead,channel="email",message=message,status="draft"); lead.status="proposal"; lead.save(update_fields=["status","updated_at"])
        ActivityLog.objects.create(lead=lead,event_type="proposal.generated",message="Proposal draft generated. No message was sent.",metadata={"outreach_id":outreach.id})
        return Response({"outreach_id":outreach.id,"status":outreach.status,"message":outreach.message})

def dashboard(request): return JsonResponse({"opportunities":Lead.objects.exclude(status="archived").count(),"qualified":Lead.objects.filter(status="qualified").count(),"proposals":Lead.objects.filter(status="proposal").count(),"replies":Lead.objects.filter(status="replied").count(),"high_match":LeadAnalysis.objects.filter(match_score__gte=80).count()})
def activity(request): return JsonResponse({"items":ActivityLogSerializer(ActivityLog.objects.all()[:50],many=True).data})
