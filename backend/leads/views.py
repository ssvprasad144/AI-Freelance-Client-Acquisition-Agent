from urllib.parse import urlsplit, urlunsplit
import re
from django.conf import settings
from django.contrib.auth import authenticate
from django.db import models, transaction
from django.http import JsonResponse
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.authtoken.models import Token
from rest_framework.decorators import action, api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from .throttles import AIThrottle, DiscoveryThrottle, LoginThrottle
from .ai_service import analyze_lead, generate_proposal
from .discovery.live_provider import LiveDiscoveryError
from .discovery.mock_provider import DiscoveryError
from .discovery.service import DiscoveryService
from .followup_service import process_due_followups as process_due_followups_service
from .acquisition import classify_reply, send_email, send_followup as send_followup_email
from .analytics import acquisition_metrics
from .models import ActivityLog, FollowUp, Lead, LeadAnalysis, Outreach, Reply
from .pagination import StandardPagination
from .serializers import ActivityLogSerializer, FollowUpSerializer, LeadSerializer, ReplySerializer

def _normalize_title(value): return re.sub(r"\s+"," ",re.sub(r"[^a-z0-9 ]"," ",str(value).lower())).strip()
def _normalize_url(value):
    try:
        parts=urlsplit(str(value).strip()); return urlunsplit(("",parts.netloc.lower().removeprefix("www."),parts.path.rstrip("/"),"",""))
    except Exception: return str(value).strip().lower().rstrip("/")

def _paginate(request,qs,serializer):
    paginator=StandardPagination(); page=paginator.paginate_queryset(qs,request)
    return paginator.get_paginated_response(serializer(page,many=True).data)

@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):
    now=timezone.now()
    discovery=ActivityLog.objects.filter(event_type="worker.discovery.heartbeat").order_by("-created_at").first()
    followup=ActivityLog.objects.filter(event_type="worker.followup.heartbeat").order_by("-created_at").first()
    def state(item,interval):
        if not item:return {"status":"unknown","last_seen":None}
        return {"status":"healthy" if (now-item.created_at).total_seconds()<=max(interval*2,120) else "stale","last_seen":item.created_at}
    return JsonResponse({"status":"ok","service":"ai-freelance-client-acquisition-agent","discovery":"web_search","workers":{"discovery":state(discovery,settings.DISCOVERY_WORKER_INTERVAL),"followups":state(followup,settings.FOLLOWUP_WORKER_INTERVAL)}})

@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([LoginThrottle])
def login(request):
    user=authenticate(request,username=str(request.data.get("username") or "").strip(),password=str(request.data.get("password") or ""))
    if not user:return Response({"detail":"Invalid username or password."},status=400)
    token,_=Token.objects.get_or_create(user=user)
    return Response({"token":token.key,"user":{"id":user.id,"username":user.username,"is_staff":user.is_staff}})

@api_view(["GET"])
def me(request): return Response({"id":request.user.id,"username":request.user.username,"is_staff":request.user.is_staff})

def _store(items):
    created=duplicates=invalid=0
    with transaction.atomic():
        for item in items:
            if not item.get("title") or not item.get("description") or not item.get("source_url"): invalid+=1; continue
            url=item["source_url"]; nt=_normalize_title(item.get("title","")); nu=_normalize_url(url); company=item.get("company","")
            if Lead.objects.filter(normalized_url=nu).exists() or Lead.objects.filter(normalized_title=nt,company__iexact=company).exists(): duplicates+=1; continue
            Lead.objects.create(title=item["title"],normalized_title=nt,normalized_url=nu,company=company,description=item["description"],source=item.get("source") or "web_search",source_url=url,lead_type=item.get("lead_type","freelance"),budget_text=item.get("budget_text",""),technologies=item.get("technologies") or [],contact_info=item.get("contact_info") or {},discovered_at=timezone.now(),posted_at=item.get("posted_at") or None,expires_at=item.get("expires_at") or None,last_verified_at=timezone.now()); created+=1
    return created,duplicates,invalid

@api_view(["POST"])
@throttle_classes([AIThrottle])
def qualify_new_leads(request):
    limit=min(max(int(request.data.get("limit",20)),1),50)
    leads=list(Lead.objects.filter(status="new",analysis__isnull=True).order_by("-discovered_at","-created_at")[:limit]); qualified=0
    for lead in leads:
        data=analyze_lead(lead); analysis,_=LeadAnalysis.objects.update_or_create(lead=lead,defaults=data)
        if analysis.relevant and analysis.match_score>=settings.QUALIFICATION_MIN_SCORE:
            lead.status="qualified"; lead.save(update_fields=["status","updated_at"]); qualified+=1
            ActivityLog.objects.create(lead=lead,event_type="lead.auto_qualified",message=f"Lead auto-qualified with score {analysis.match_score}.",metadata={"model":analysis.model,"match_score":analysis.match_score,"threshold":settings.QUALIFICATION_MIN_SCORE})
    return Response({"status":"success","analyzed":len(leads),"qualified":qualified,"threshold":settings.QUALIFICATION_MIN_SCORE,"remaining_new":Lead.objects.filter(status="new").count()})

@api_view(["GET"])
def followups(request): return _paginate(request,FollowUp.objects.filter(status__in=["draft","approved"]).select_related("lead").order_by("scheduled_at"),FollowUpSerializer)

@api_view(["POST"])
def create_followup(request,pk=None):
    lead_id=pk or request.data.get("lead_id")
    if not lead_id:return Response({"detail":"lead_id is required."},status=400)
    try:lead=Lead.objects.get(pk=lead_id)
    except Lead.DoesNotExist:return Response({"detail":"Lead not found."},status=404)
    scheduled=request.data.get("scheduled_at"); message=str(request.data.get("message") or "").strip()
    if not scheduled or not message:return Response({"detail":"scheduled_at and message are required."},status=400)
    followup=FollowUp.objects.create(lead=lead,scheduled_at=scheduled,message=message,status="draft")
    ActivityLog.objects.create(lead=lead,event_type="followup.created",message="Follow-up draft created. No message was sent.",metadata={"followup_id":followup.id})
    return Response(FollowUpSerializer(followup).data)

@api_view(["POST"])
def process_due_followups(request): return Response(process_due_followups_service())
@api_view(["GET"])
def due_followups(request): return _paginate(request,FollowUp.objects.filter(status="due").select_related("lead").order_by("scheduled_at"),FollowUpSerializer)
@api_view(["GET"])
def qualified_leads(request):
    now=timezone.now(); qs=Lead.objects.filter(status__in=["qualified","proposal"]).filter(models.Q(expires_at__isnull=True)|models.Q(expires_at__gt=now)).order_by("-updated_at")
    return _paginate(request,qs,LeadSerializer)

@api_view(["POST"])
def approve_followup(request,pk):
    try:followup=FollowUp.objects.get(pk=pk)
    except FollowUp.DoesNotExist:return Response({"detail":"Follow-up not found."},status=404)
    if followup.status!="draft":return Response({"detail":"Follow-up is not in draft state."},status=400)
    followup.status="approved"; followup.approved_at=timezone.now(); followup.save(update_fields=["status","approved_at"])
    ActivityLog.objects.create(lead=followup.lead,event_type="followup.approved",message="Follow-up approved by user. No message was sent.",metadata={"followup_id":followup.id})
    return Response({**FollowUpSerializer(followup).data,"sent":False})

@api_view(["POST"])
@throttle_classes([DiscoveryThrottle])
def run_discovery(request):
    query=str(request.data.get("query") or settings.DEFAULT_DISCOVERY_QUERY).strip(); source=str(request.data.get("source") or "live").lower()
    try:result=DiscoveryService().discover(query,source)
    except (LiveDiscoveryError,DiscoveryError) as exc:return Response({"status":"error","detail":str(exc)},status=502)
    items=result.get("leads",[]); created,duplicates,invalid=_store(items)
    payload={"query":query,"source":result.get("source",source),"discovered":len(items),"created":created,"duplicates":duplicates,"invalid":invalid,"model":result.get("model","unknown")}
    ActivityLog.objects.create(event_type="discovery.completed",message=f"Discovery completed from {payload['source']}.",metadata=payload)
    return Response({"status":"success",**payload})

@api_view(["GET"])
def replies(request): return _paginate(request,Reply.objects.select_related("lead").order_by("-created_at"),ReplySerializer)

@api_view(["POST"])
def create_reply(request,pk):
    try:lead=Lead.objects.get(pk=pk)
    except Lead.DoesNotExist:return Response({"detail":"Lead not found."},status=404)
    message=str(request.data.get("message") or "").strip()
    if not message:return Response({"detail":"message is required."},status=400)
    reply=Reply.objects.create(lead=lead,channel=str(request.data.get("channel") or "email"),message=message,intent="needs_review")
    try:
        classification=classify_reply(reply)
        reply.sentiment=classification.get("sentiment",""); reply.intent=classification.get("intent",""); reply.save(update_fields=["sentiment","intent"])
    except Exception as exc:
        classification={"recommended_action":"Review reply manually.","error":str(exc)}
    lead.status="replied"; lead.save(update_fields=["status","updated_at"])
    ActivityLog.objects.create(lead=lead,event_type="lead.reply_received",message="Reply recorded manually.",metadata={"reply_id":reply.id})
    return Response({**ReplySerializer(reply).data,"classification":classification},status=201)

class LeadViewSet(viewsets.ModelViewSet):
    queryset=Lead.objects.all().prefetch_related("analysis"); serializer_class=LeadSerializer
    @action(detail=True,methods=["post"],throttle_classes=[AIThrottle])
    def analyze(self,request,pk=None):
        lead=self.get_object(); data=analyze_lead(lead); analysis,_=LeadAnalysis.objects.update_or_create(lead=lead,defaults=data)
        if analysis.relevant and analysis.match_score>=settings.QUALIFICATION_MIN_SCORE and lead.status=="new":lead.status="qualified"; lead.save(update_fields=["status","updated_at"])
        ActivityLog.objects.create(lead=lead,event_type="lead.analyzed",message=f"Lead analyzed with score {analysis.match_score}.",metadata={"model":analysis.model,"match_score":analysis.match_score})
        return Response(LeadSerializer(lead).data)
    @action(detail=True,methods=["post"],throttle_classes=[AIThrottle])
    def proposal(self,request,pk=None):
        lead=self.get_object(); analysis=getattr(lead,"analysis",None)
        if not analysis:return Response({"detail":"Analyze the lead first."},status=400)
        message=generate_proposal(lead,analysis); outreach=Outreach.objects.create(lead=lead,channel="email",message=message,status="draft"); lead.status="proposal"; lead.save(update_fields=["status","updated_at"])
        ActivityLog.objects.create(lead=lead,event_type="proposal.generated",message="Proposal draft generated. No message was sent.",metadata={"outreach_id":outreach.id})
        return Response({"outreach_id":outreach.id,"status":"draft","message":message})
    @action(detail=True,methods=["post"])
    def approve_proposal(self,request,pk=None):
        lead=self.get_object(); outreach=lead.outreach.filter(status="draft").order_by("-created_at").first()
        if not outreach:return Response({"detail":"Generate a proposal draft first."},status=400)
        outreach.status="approved"; outreach.approved_at=timezone.now(); outreach.save(update_fields=["status","approved_at"])
        ActivityLog.objects.create(lead=lead,event_type="proposal.approved",message="Proposal approved by user. No message was sent.",metadata={"outreach_id":outreach.id})
        return Response({"outreach_id":outreach.id,"status":"approved","sent":False,"message":outreach.message})
    @action(detail=True,methods=["post"])
    def set_status(self,request,pk=None):
        lead=self.get_object(); new_status=str(request.data.get("status") or "").strip()
        if new_status not in {x[0] for x in Lead.STATUS}:return Response({"detail":"Invalid lead status."},status=400)
        lead.status=new_status; lead.save(update_fields=["status","updated_at"]); ActivityLog.objects.create(lead=lead,event_type="lead.status_changed",message=f"Lead status changed to {new_status}.",metadata={"status":new_status})
        return Response(LeadSerializer(lead).data)

DISCOVERY_PROFILES=[
    {"id":"ai-automation","label":"AI & Automation","query":"current public freelance opportunities for AI products, AI agents, workflow automation, Python automation and business automation"},
    {"id":"django-fullstack","label":"Django & Full-Stack","query":"current public freelance opportunities for Django, Django REST Framework, Python backend, React and full-stack development"},
    {"id":"interactive-web","label":"React & Three.js","query":"current public freelance opportunities for React, Three.js, WebGL, interactive websites and 3D web development"},
    {"id":"startup-build","label":"Startup MVPs","query":"current public freelance opportunities from startups seeking an MVP, SaaS prototype, AI MVP or full-stack product developer"},
]

@api_view(["GET"])
def discovery_profiles(request):
    return Response({"profiles":DISCOVERY_PROFILES})

@api_view(["GET"])
def analytics(request):
    return Response(acquisition_metrics())

@api_view(["POST"])
def send_followup(request,pk):
    try: followup=FollowUp.objects.select_related("lead").get(pk=pk)
    except FollowUp.DoesNotExist: return Response({"detail":"Follow-up not found."},status=404)
    try: return Response(send_followup_email(followup))
    except ValueError as exc: return Response({"detail":str(exc),"sent":False},status=400)
    except Exception as exc:
        ActivityLog.objects.create(lead=followup.lead,event_type="followup.error",message="Configured follow-up provider failed.",metadata={"followup_id":followup.id,"error":str(exc)})
        return Response({"detail":"Outbound provider failed.","sent":False},status=502)

@api_view(["POST"])
def send_outreach(request,pk):
    try: outreach=Outreach.objects.select_related("lead").get(pk=pk)
    except Outreach.DoesNotExist: return Response({"detail":"Outreach not found."},status=404)
    try: return Response(send_email(outreach))
    except ValueError as exc: return Response({"detail":str(exc),"sent":False},status=400)
    except Exception as exc:
        ActivityLog.objects.create(lead=outreach.lead,event_type="outreach.error",message="Configured outreach provider failed.",metadata={"outreach_id":outreach.id,"error":str(exc)})
        return Response({"detail":"Outbound provider failed.","sent":False},status=502)

def dashboard(request):
    now=timezone.now(); active=Lead.objects.exclude(status="archived").filter(models.Q(expires_at__isnull=True)|models.Q(expires_at__gt=now)); last=ActivityLog.objects.filter(event_type="discovery.completed").order_by("-created_at").first()
    return JsonResponse({"opportunities":active.count(),"qualified":Lead.objects.filter(status="qualified").count(),"proposals":Lead.objects.filter(status="proposal").count(),"replies":Lead.objects.filter(status="replied").count(),"high_match":LeadAnalysis.objects.filter(match_score__gte=80).count(),"followups_pending":FollowUp.objects.filter(status="draft").count(),"followups_upcoming":FollowUp.objects.filter(status="approved",scheduled_at__gt=now).count(),"followups_due":FollowUp.objects.filter(status="due").count(),"last_discovery_at":last.created_at if last else None,"last_discovery":last.metadata if last else None})

@api_view(["GET"])
def activity(request):return _paginate(request,ActivityLog.objects.all(),ActivityLogSerializer)
