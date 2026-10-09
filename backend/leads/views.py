from urllib.parse import urlsplit, urlunsplit
import logging
import time
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
from .ai_service import analyze_lead, analysis_fingerprint, generate_proposal
from .discovery.live_provider import LiveDiscoveryError
from .discovery.mock_provider import DiscoveryError
from .discovery.service import DiscoveryService
from .discovery.profiles import public_profiles, strategy_performance
from .discovery_cycle import run_discovery_cycle
from .lead_optimizer import local_lead_score, should_ai_qualify, ai_skip_analysis
from .followup_service import process_due_followups as process_due_followups_service
from .followup_intelligence import create_sequence, cancel_if_stopped
from .acquisition import classify_reply, send_email, send_followup as send_followup_email
from .outreach_adapters import resolve_outreach_destination
from .proposal_service import create_proposal, current_version, revise_proposal, restore_version
from .client_service import sync_lead_client, record_message, generate_client_intelligence
from .meeting_service import sync_meeting_context, apply_meeting_status, apply_meeting_status
from .learning import log_acquisition_event, refresh_learning
from .acquisition_orchestrator import build_queue, ensure_opportunity, execute_action, recalculate_opportunities
from .outreach_intelligence import build_outreach_plans, create_plan, channel_metrics, mark_approved

logger = logging.getLogger(__name__)


from .revenue_intelligence import upsert_revenue, revenue_metrics, optimization_report
from .analytics import acquisition_metrics
from .models import ActivityLog, FollowUp, FollowUpSequence, Lead, LeadAnalysis, Outreach, Proposal, Reply, Client, Contact, Conversation, Meeting, AcquisitionEvent, LearningStat, AcquisitionOpportunity, OutreachPlan, RevenueRecord
from .pagination import StandardPagination
from .serializers import ActivityLogSerializer, FollowUpSerializer, FollowUpSequenceSerializer, LeadSerializer, ReplySerializer, OutreachSerializer, ProposalSerializer, ClientSerializer, ContactSerializer, ConversationSerializer, MeetingSerializer, AcquisitionEventSerializer, LearningStatSerializer, ClientIntelligenceSerializer, AcquisitionOpportunitySerializer, OutreachPlanSerializer, RevenueRecordSerializer

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
    from django.db import connection
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        database="ok"
    except Exception:
        return JsonResponse({"status":"unhealthy","database":"error","service":"ai-freelance-client-acquisition-agent"},status=503)
    now=timezone.now()
    supervisor=ActivityLog.objects.filter(event_type="automation.cycle.completed").order_by("-created_at").first()
    supervisor_failure=ActivityLog.objects.filter(event_type="automation.cycle.failed").order_by("-created_at").first()
    def state(item, interval):
        if not item:
            return {"status":"unknown","last_seen":None}
        age=(now-item.created_at).total_seconds()
        return {"status":"healthy" if age<=max(interval*2,120) else "stale","last_seen":item.created_at}
    supervisor_state=state(supervisor, 180)
    discovery_event=ActivityLog.objects.filter(event_type__in=["discovery.completed","discovery.skipped","discovery.cache_hit"]).order_by("-created_at").first()
    followup_event=ActivityLog.objects.filter(event_type__in=["cron.followup.completed","cron.followup.failed"]).order_by("-created_at").first()
    discovery_state=state(discovery_event, 900)
    followup_state=state(followup_event, 1800)
    stale=supervisor_state["status"]=="stale"
    from datetime import timedelta
    recent_failures=ActivityLog.objects.filter(
        event_type__in=[
            "automation.cycle.failed","automation.discovery_failed",
            "automation.owner_failed","automation.followups_failed",
            "automation.action_failed",
        ],
        created_at__gte=now-timedelta(hours=1),
    ).count()
    recent_recoveries=ActivityLog.objects.filter(
        event_type__in=["followup.recovered","outreach.recovered"],
        created_at__gte=now-timedelta(hours=1),
    ).count()
    payload={"status":"degraded" if stale or recent_failures else "healthy",
             "database":database,"service":"ai-freelance-client-acquisition-agent",
             "discovery":"web_search",
             "cron_jobs":{"supervisor":supervisor_state,"discovery":discovery_state,"followups":followup_state},
             "observability":{"recent_failures_1h":recent_failures,"outbound_recoveries_1h":recent_recoveries}}
    return JsonResponse(payload,status=503 if stale or recent_failures else 200)

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





def _owned_leads(request):
    return Lead.objects.filter(owner=request.user)

def _owned_clients(request):
    return Client.objects.filter(owner=request.user)

def _owned_lead(request, pk):
    return _owned_leads(request).filter(pk=pk).first()

def _parse_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized=value.strip().lower()
        if normalized in {"true","1","yes","on"}: return True
        if normalized in {"false","0","no","off"}: return False
    raise ValueError("Expected a boolean value.")

def _proposal_delivery(lead):
    destination = resolve_outreach_destination(lead)
    return {"medium": destination.medium, "action_type": destination.action_type, "action_url": destination.url}

def _store(items):
    created=duplicates=invalid=0
    with transaction.atomic():
        for item in items:
            if not item.get("title") or not item.get("description") or not item.get("source_url"): invalid+=1; continue
            url=item["source_url"]; nt=_normalize_title(item.get("title","")); nu=_normalize_url(url); company=item.get("company","")
            if Lead.objects.filter(normalized_url=nu).exists() or Lead.objects.filter(normalized_title=nt,company__iexact=company).exists(): duplicates+=1; continue
            Lead.objects.create(title=item["title"],normalized_title=nt,normalized_url=nu,company=company,description=item["description"],source=item.get("source") or "web_search",source_url=url,action_url=item.get("action_url") or url,lead_type=item.get("lead_type","freelance"),budget_text=item.get("budget_text",""),technologies=item.get("technologies") or [],contact_info=item.get("contact_info") or {},discovered_at=timezone.now(),posted_at=item.get("posted_at") or None,expires_at=item.get("expires_at") or None,last_verified_at=timezone.now()); created+=1
    return created,duplicates,invalid

@api_view(["POST"])
@throttle_classes([AIThrottle])
def qualify_new_leads(request):
    try: limit=min(max(int(request.data.get("limit",20)),1),50)
    except (TypeError,ValueError): return Response({"detail":"limit must be an integer."},status=400)
    now=timezone.now()
    leads=list(_owned_leads(request).filter(status="new",analysis__isnull=True).filter(models.Q(expires_at__isnull=True)|models.Q(expires_at__gt=now)).order_by("-discovered_at","-created_at")[:limit]); qualified=0; locally_filtered=0
    for lead in leads:
        local=local_lead_score(lead)
        if not should_ai_qualify(lead):
            data=ai_skip_analysis(lead,local); locally_filtered+=1
        else:
            data=analyze_lead(lead)
        analysis,_=LeadAnalysis.objects.update_or_create(lead=lead,defaults=data)
        if analysis.relevant and analysis.match_score>=settings.QUALIFICATION_MIN_SCORE:
            lead.status="qualified"; lead.save(update_fields=["status","updated_at"]); qualified+=1
            ActivityLog.objects.create(lead=lead,event_type="lead.auto_qualified",message=f"Lead auto-qualified with score {analysis.match_score}.",metadata={"model":analysis.model,"match_score":analysis.match_score,"threshold":settings.QUALIFICATION_MIN_SCORE})
    return Response({"status":"success","analyzed":len(leads),"qualified":qualified,"locally_filtered":locally_filtered,"ai_calls":len(leads)-locally_filtered,"threshold":settings.QUALIFICATION_MIN_SCORE,"remaining_new":_owned_leads(request).filter(status="new").count()})

@api_view(["GET"])
def followups(request): return _paginate(request,FollowUp.objects.filter(lead__owner=request.user,status__in=["draft","approved"]).select_related("lead").order_by("scheduled_at"),FollowUpSerializer)

@api_view(["POST"])
def create_followup(request,pk=None):
    lead_id=pk or request.data.get("lead_id")
    if not lead_id:return Response({"detail":"lead_id is required."},status=400)
    lead=_owned_lead(request, lead_id)
    if not lead:return Response({"detail":"Lead not found."},status=404)
    scheduled=request.data.get("scheduled_at"); message=str(request.data.get("message") or "").strip()
    if not scheduled or not message:return Response({"detail":"scheduled_at and message are required."},status=400)
    followup=FollowUp.objects.create(lead=lead,scheduled_at=scheduled,message=message,status="draft")
    ActivityLog.objects.create(lead=lead,event_type="followup.created",message="Follow-up draft created. No message was sent.",metadata={"followup_id":followup.id})
    return Response(FollowUpSerializer(followup).data)

@api_view(["POST"])
def process_due_followups(request): return Response(process_due_followups_service())
@api_view(["GET"])
def due_followups(request): return _paginate(request,FollowUp.objects.filter(lead__owner=request.user,status="due").select_related("lead").order_by("scheduled_at"),FollowUpSerializer)
@api_view(["GET"])
def qualified_leads(request):
    now=timezone.now(); qs=_owned_leads(request).filter(status__in=["qualified","proposal"]).filter(models.Q(expires_at__isnull=True)|models.Q(expires_at__gt=now)).order_by("-updated_at")
    return _paginate(request,qs,LeadSerializer)

@api_view(["POST"])
def approve_followup(request,pk):
    try:followup=FollowUp.objects.select_related("lead").get(pk=pk,lead__owner=request.user)
    except FollowUp.DoesNotExist:return Response({"detail":"Follow-up not found."},status=404)
    if followup.status!="draft":return Response({"detail":"Follow-up is not in draft state."},status=400)
    followup.status="approved"; followup.approved_at=timezone.now(); followup.save(update_fields=["status","approved_at"])
    ActivityLog.objects.create(lead=followup.lead,event_type="followup.approved",message="Follow-up approved by user. No message was sent.",metadata={"followup_id":followup.id})
    return Response({**FollowUpSerializer(followup).data,"sent":False})

@api_view(["POST"])
@throttle_classes([DiscoveryThrottle])
def run_discovery(request):
    query=str(request.data.get("query") or settings.DEFAULT_DISCOVERY_QUERY).strip()
    source=str(request.data.get("source") or "live").lower()
    try: limit=min(max(int(request.data.get("limit",settings.DISCOVERY_MAX_RESULTS)),1),settings.DISCOVERY_MAX_RESULTS)
    except (TypeError,ValueError): return Response({"detail":"limit must be an integer."},status=400)
    started_at = time.monotonic()
    try:
        payload=run_discovery_cycle(query=query,source=source,qualification_limit=limit,profile_id="manual",owner=request.user)
    except (LiveDiscoveryError,DiscoveryError) as exc:
        elapsed_ms = round((time.monotonic() - started_at) * 1000)
        logger.exception(
            "Discovery request failed (source=%s, model=%s, query_chars=%d, elapsed_ms=%d)",
            source,
            getattr(settings, "DISCOVERY_MODEL", "unknown"),
            len(query),
        )
        return Response({"status":"error","detail":str(exc),"elapsed_ms":elapsed_ms},status=502)
    except Exception:
        elapsed_ms = round((time.monotonic() - started_at) * 1000)
        logger.exception(
            "Unexpected discovery error (source=%s, model=%s, query_chars=%d, elapsed_ms=%d)",
            source,
            getattr(settings, "DISCOVERY_MODEL", "unknown"),
            len(query),
            elapsed_ms,
        )
        return Response({"status":"error","detail":"Unexpected discovery failure. Check backend logs for the traceback.","elapsed_ms":elapsed_ms},status=500)
    return Response({"status":"success",**payload,"elapsed_ms":round((time.monotonic() - started_at) * 1000)})

@api_view(["GET"])
def replies(request): return _paginate(request,Reply.objects.filter(lead__owner=request.user).select_related("lead").order_by("-created_at"),ReplySerializer)

@api_view(["POST"])
def create_reply(request,pk):
    lead=_owned_lead(request, pk)
    if not lead:return Response({"detail":"Lead not found."},status=404)
    message=str(request.data.get("message") or "").strip()
    if not message:return Response({"detail":"message is required."},status=400)
    reply=Reply.objects.create(lead=lead,channel=str(request.data.get("channel") or "email"),message=message,intent="needs_review")
    try:
        classification=classify_reply(reply)
        reply.sentiment=classification.get("sentiment",""); reply.intent=classification.get("intent",""); reply.urgency=classification.get("urgency",""); reply.confidence=int(classification.get("confidence",0) or 0); reply.extracted_questions=classification.get("extracted_questions",[]) or []; reply.recommended_action=classification.get("recommended_action",""); reply.suggested_response=classification.get("suggested_response",""); reply.next_action=classification.get("next_action",""); reply.save(update_fields=["sentiment","intent","urgency","confidence","extracted_questions","recommended_action","suggested_response","next_action"])
    except Exception as exc:
        classification={"recommended_action":"Review reply manually.","error":str(exc)}
    lead.status="replied"; lead.save(update_fields=["status","updated_at"])
    client,contact=sync_lead_client(lead)
    if client: record_message(client,lead,reply.channel,"inbound",message,{"reply_id":reply.id},contact)
    log_acquisition_event(lead,"replied",{"reply_id":reply.id})
    for sequence in FollowUpSequence.objects.filter(lead=lead,status="active"):
        cancel_if_stopped(sequence)
    ActivityLog.objects.create(lead=lead,event_type="lead.reply_received",message="Reply recorded and analyzed manually.",metadata={"reply_id":reply.id})
    return Response({**ReplySerializer(reply).data,"classification":classification},status=201)

class LeadViewSet(viewsets.ModelViewSet):
    queryset=Lead.objects.all().prefetch_related("analysis")
    serializer_class=LeadSerializer

    def get_queryset(self):
        return Lead.objects.filter(owner=self.request.user).prefetch_related("analysis")

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)
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
        if analysis.input_fingerprint and analysis.input_fingerprint != analysis_fingerprint(lead):
            return Response({"detail":"Lead changed after analysis. Re-analyze before generating a proposal."},status=409)
        if not (analysis.relevant and analysis.match_score>=settings.QUALIFICATION_MIN_SCORE):
            return Response({"detail":f"Only qualified leads can generate proposals. Required score: {settings.QUALIFICATION_MIN_SCORE}."},status=400)
        delivery=_proposal_delivery(lead)
        sync_lead_client(lead)
        if lead.client_id and not hasattr(lead.client,"intelligence"):
            generate_client_intelligence(lead.client)
        proposal,version=create_proposal(lead,analysis,delivery["medium"])
        outreach=Outreach.objects.create(lead=lead,proposal=proposal,channel=delivery["medium"],medium=delivery["medium"],action_type=delivery["action_type"],destination_url=delivery["action_url"] or "",message=version.content,status="draft")
        lead.status="proposal"; lead.save(update_fields=["status","updated_at"])
        log_acquisition_event(lead,"proposal_generated",{"proposal_id":proposal.id,"outreach_id":outreach.id})
        ActivityLog.objects.create(lead=lead,event_type="proposal.generated",message="Versioned proposal draft generated. No message was sent.",metadata={"outreach_id":outreach.id,"proposal_id":proposal.id,"version":version.version_number})
        return Response({"outreach_id":outreach.id,"proposal_id":proposal.id,"version":version.version_number,"status":"draft","message":version.content,"medium":outreach.medium,"action_type":outreach.action_type,"destination_url":outreach.destination_url,"lead_source_url":lead.source_url,"can_send":outreach.medium=="email"})
    @action(detail=True,methods=["post"])
    def approve_proposal(self,request,pk=None):
        lead=self.get_object(); outreach=lead.outreach.filter(status="draft").order_by("-created_at").first()
        if not outreach:return Response({"detail":"Generate a proposal draft first."},status=400)
        if outreach.proposal_id:
            proposal=outreach.proposal; proposal.status="approved"; proposal.approved_at=timezone.now(); proposal.save(update_fields=["status","approved_at","updated_at"])
            version=current_version(proposal)
            if version: outreach.message=version.content
        outreach.status="approved"; outreach.approved_at=timezone.now(); outreach.save(update_fields=["status","approved_at","message"])
        ActivityLog.objects.create(lead=lead,event_type="proposal.approved",message="Proposal approved by user. No message was sent.",metadata={"outreach_id":outreach.id,"proposal_id":outreach.proposal_id})
        log_acquisition_event(lead,"approved",{"proposal_id":outreach.proposal_id,"outreach_id":outreach.id})
        return Response({"outreach_id":outreach.id,"proposal_id":outreach.proposal_id,"status":"approved","sent":False,"message":outreach.message,"medium":outreach.medium,"action_type":outreach.action_type,"destination_url":outreach.destination_url,"can_send":outreach.medium=="email"})
    @action(detail=True,methods=["post"])
    def set_status(self,request,pk=None):
        lead=self.get_object(); new_status=str(request.data.get("status") or "").strip()
        if new_status not in {x[0] for x in Lead.STATUS}:return Response({"detail":"Invalid lead status."},status=400)
        lead.status=new_status
        lead.save(update_fields=["status","updated_at"])
        event_map={"won":"won","lost":"lost","qualified":"qualified"}
        if new_status in event_map: log_acquisition_event(lead,event_map[new_status])
        if new_status in {"won","lost","archived"}:
            FollowUpSequence.objects.filter(lead=lead,status="active").update(status="completed")
            FollowUp.objects.filter(lead=lead,status__in=["draft","approved","due"]).update(status="cancelled")
            if lead.client_id:
                lead.client.status="won" if new_status=="won" else ("lost" if new_status=="lost" else "archived")
                lead.client.save(update_fields=["status","updated_at"])
        ActivityLog.objects.create(lead=lead,event_type="lead.status_changed",message=f"Lead status changed to {new_status}.",metadata={"status":new_status})
        return Response(LeadSerializer(lead).data)

@api_view(["GET"])
def proposal_workspace(request, pk):
    proposal=Proposal.objects.filter(lead__owner=request.user).prefetch_related("versions").filter(pk=pk).first()
    if not proposal: return Response({"detail":"Proposal not found."},status=404)
    version=current_version(proposal)
    return Response({**ProposalSerializer(proposal).data,"current_content":version.content if version else ""})

@api_view(["PUT"])
def edit_proposal(request, pk):
    proposal=Proposal.objects.filter(lead__owner=request.user,pk=pk).first()
    if not proposal: return Response({"detail":"Proposal not found."},status=404)
    content=str(request.data.get("content") or "").strip()
    if not content: return Response({"detail":"content is required."},status=400)
    number=proposal.versions.order_by("-version_number").values_list("version_number",flat=True).first() or 0
    version=proposal.versions.create(version_number=number+1,content=content,source="user",instruction="Manual workspace edit")
    proposal.current_version=version.version_number; proposal.status="draft"; proposal.save(update_fields=["current_version","status","updated_at"])
    proposal.outreach.update(message=content,status="draft")
    return Response({**ProposalSerializer(proposal).data,"current_content":content})

@api_view(["POST"])
def revise_proposal_view(request, pk):
    proposal=Proposal.objects.filter(lead__owner=request.user,pk=pk).first()
    if not proposal: return Response({"detail":"Proposal not found."},status=404)
    try: version=revise_proposal(proposal,str(request.data.get("instruction") or ""))
    except ValueError as exc: return Response({"detail":str(exc)},status=400)
    proposal.outreach.update(message=version.content,status="draft")
    return Response({**ProposalSerializer(proposal).data,"current_content":version.content})

@api_view(["POST"])
def restore_proposal_version(request, pk):
    proposal=Proposal.objects.filter(lead__owner=request.user,pk=pk).first()
    if not proposal: return Response({"detail":"Proposal not found."},status=404)
    try: version=restore_version(proposal,int(request.data.get("version_number")))
    except (ValueError,TypeError): return Response({"detail":"Valid version_number is required."},status=400)
    proposal.outreach.update(message=version.content,status="draft")
    return Response({**ProposalSerializer(proposal).data,"current_content":version.content})

@api_view(["GET"])
def proposals(request):
    return _paginate(request,Proposal.objects.filter(lead__owner=request.user).select_related("lead").prefetch_related("versions").order_by("-updated_at"),ProposalSerializer)

@api_view(["POST"])
def create_followup_sequence(request, pk):
    lead=_owned_lead(request, pk)
    if not lead: return Response({"detail":"Lead not found."},status=404)
    try: max_steps=max(1,min(int(request.data.get("max_steps",3)),5))
    except (TypeError,ValueError): max_steps=3
    delays=request.data.get("delays_days") or [3,5,7]
    if not isinstance(delays,list) or not delays: return Response({"detail":"delays_days must be a non-empty array."},status=400)
    try: delays=[int(x) for x in delays]
    except (TypeError,ValueError): return Response({"detail":"delays_days must contain integers."},status=400)
    if any(x<=0 for x in delays): return Response({"detail":"delays_days must contain positive day values."},status=400)
    sequence,followup=create_sequence(lead,delays,max_steps)
    ActivityLog.objects.create(lead=lead,event_type="followup.sequence_created",message="Intelligent follow-up sequence created as drafts. No message was sent.",metadata={"sequence_id":sequence.id,"first_followup_id":followup.id})
    return Response({"sequence":FollowUpSequenceSerializer(sequence).data,"first_followup":FollowUpSerializer(followup).data},status=201)

@api_view(["GET"])
def followup_sequences(request):
    return _paginate(request,FollowUpSequence.objects.filter(lead__owner=request.user).select_related("lead").prefetch_related("followups").order_by("-created_at"),FollowUpSequenceSerializer)

@api_view(["POST"])
def cancel_followup_sequence(request, pk):
    sequence=FollowUpSequence.objects.filter(lead__owner=request.user,pk=pk).first()
    if not sequence: return Response({"detail":"Sequence not found."},status=404)
    sequence.status="cancelled"; sequence.save(update_fields=["status","updated_at"])
    FollowUp.objects.filter(sequence=sequence,status__in=["draft","approved","due"]).update(status="cancelled")
    return Response(FollowUpSequenceSerializer(sequence).data)

@api_view(["GET"])
def discovery_profiles(request):
    return Response({"profiles":public_profiles(),"strategy_performance":strategy_performance()})

@api_view(["GET"])
def analytics(request):
    return Response(acquisition_metrics(owner=request.user))

@api_view(["POST"])
def send_followup(request,pk):
    followup=FollowUp.objects.select_related("lead").filter(lead__owner=request.user,pk=pk).first()
    if not followup: return Response({"detail":"Follow-up not found."},status=404)
    claimed=FollowUp.objects.filter(pk=pk,lead__owner=request.user,status="due").update(status="sending")
    if not claimed:
        return Response({"detail":"Follow-up is not due or is already being/sent."},status=409)
    followup.refresh_from_db()
    try:
        result=send_followup_email(followup)
        return Response(result)
    except ValueError as exc:
        followup.status="due"; followup.save(update_fields=["status"])
        return Response({"detail":str(exc),"sent":False},status=400)
    except Exception as exc:
        followup.status="send_uncertain"; followup.save(update_fields=["status"])
        ActivityLog.objects.create(lead=followup.lead,event_type="followup.error",message="Configured follow-up provider failed after an ambiguous delivery attempt; automatic retry is blocked.",metadata={"followup_id":followup.id,"error":str(exc)[:500],"requires_reconciliation":True})
        return Response({"detail":"Outbound provider failed; delivery status is uncertain and requires reconciliation.","sent":False},status=502)

@api_view(["POST"])
def send_outreach(request,pk):
    outreach=Outreach.objects.select_related("lead").filter(lead__owner=request.user,pk=pk).first()
    if not outreach: return Response({"detail":"Outreach not found."},status=404)
    claimed=Outreach.objects.filter(pk=pk,lead__owner=request.user,status="approved").update(status="sending")
    if not claimed:
        return Response({"detail":"Outreach is not actionable or has already been sent."},status=409)
    outreach.refresh_from_db()
    try:
        result=send_email(outreach)
        plan=OutreachPlan.objects.filter(lead__owner=request.user,lead=outreach.lead,channel=outreach.medium,message=outreach.message,status="approved").order_by("-updated_at").first()
        if plan:
            from .outreach_intelligence import record_attempt_for_outreach
            record_attempt_for_outreach(plan)
        outreach.status="sent"; outreach.sent_at=timezone.now(); outreach.save(update_fields=["status","sent_at"])
        log_acquisition_event(outreach.lead,"sent",{"outreach_id":outreach.id})
        client,contact=sync_lead_client(outreach.lead)
        if client: record_message(client,outreach.lead,outreach.medium,"outbound",outreach.message,{"outreach_id":outreach.id},contact)
        return Response(result)
    except ValueError as exc:
        outreach.status="approved"; outreach.save(update_fields=["status"])
        return Response({"detail":str(exc),"sent":False},status=400)
    except Exception as exc:
        outreach.status="send_uncertain"; outreach.save(update_fields=["status"])
        ActivityLog.objects.create(lead=outreach.lead,event_type="outreach.error",message="Configured outreach provider failed after an ambiguous delivery attempt; automatic retry is blocked.",metadata={"outreach_id":outreach.id,"error":str(exc)[:500],"requires_reconciliation":True})
        return Response({"detail":"Outbound provider failed; delivery status is uncertain and requires reconciliation.","sent":False},status=502)


@api_view(["GET"])
def outreach_ready(request):
    rows=[]
    qs=Outreach.objects.filter(lead__owner=request.user).select_related("lead","proposal").filter(status__in=["draft","approved","opened"]).order_by("-created_at")
    for item in qs:
        rows.append({
            "id":item.id,"lead_id":item.lead_id,"lead_title":item.lead.title,
            "lead_source":item.lead.source,"medium":item.medium,"action_type":item.action_type,
            "destination_url":item.destination_url,"message":item.message,"status":item.status,
        })
    return Response(rows)

@api_view(["POST"])
def open_outreach(request,pk):
    item=Outreach.objects.filter(lead__owner=request.user,pk=pk).first()
    if not item: return Response({"detail":"Outreach not found."},status=404)
    if item.status=="draft": item.status="opened"
    item.opened_at=item.opened_at or timezone.now()
    item.save(update_fields=["status","opened_at"])
    return Response({"id":item.id,"status":item.status,"destination_url":item.destination_url})

@api_view(["POST"])
def mark_outreach_submitted(request,pk):
    item=Outreach.objects.filter(lead__owner=request.user,pk=pk).first()
    if not item: return Response({"detail":"Outreach not found."},status=404)
    if item.medium=="email": return Response({"detail":"Email outreach must be sent through the email action."},status=400)
    claimed=Outreach.objects.filter(lead__owner=request.user,pk=pk,status__in=["draft","approved","opened"]).update(status="sending")
    if not claimed: return Response({"detail":"Outreach is not actionable or has already been submitted."},status=409)
    item.refresh_from_db()
    item.status="submitted"; item.submitted_at=timezone.now()
    item.save(update_fields=["status","submitted_at"])
    plan=OutreachPlan.objects.filter(lead=item.lead,channel=item.medium,message=item.message,status="approved").order_by("-updated_at").first()
    if plan:
        from .outreach_intelligence import record_attempt_for_outreach
        record_attempt_for_outreach(plan,item.submitted_at)
    OutreachPlan.objects.filter(lead=item.lead,channel=item.medium,message=item.message,status="approved").update(status="sent",sent_at=timezone.now())
    log_acquisition_event(item.lead,"sent",{"outreach_id":item.id,"manual":True,"medium":item.medium})
    if item.lead.status not in {"replied","won","lost","archived"}:
        item.lead.status="contacted"; item.lead.save(update_fields=["status","updated_at"])
    return Response({"id":item.id,"status":item.status})

@api_view(["GET"])
def dashboard(request):
    now=timezone.now(); active=_owned_leads(request).exclude(status="archived").filter(models.Q(expires_at__isnull=True)|models.Q(expires_at__gt=now)); last=ActivityLog.objects.filter(lead__owner=request.user,event_type="discovery.completed").order_by("-created_at").first()
    return JsonResponse({"opportunities":active.count(),"qualified":_owned_leads(request).filter(status="qualified").count(),"proposals":_owned_leads(request).filter(status="proposal").count(),"replies":_owned_leads(request).filter(status="replied").count(),"high_match":LeadAnalysis.objects.filter(lead__owner=request.user,match_score__gte=80).count(),"followups_pending":FollowUp.objects.filter(lead__owner=request.user,status="draft").count(),"followups_upcoming":FollowUp.objects.filter(lead__owner=request.user,status="approved",scheduled_at__gt=now).count(),"followups_due":FollowUp.objects.filter(lead__owner=request.user,status="due").count(),"last_discovery_at":last.created_at if last else None,"last_discovery":last.metadata if last else None})

@api_view(["GET"])
def activity(request):return _paginate(request,ActivityLog.objects.filter(models.Q(lead__owner=request.user)|models.Q(lead__isnull=True)).order_by("-created_at"),ActivityLogSerializer)


@api_view(["GET"])
def clients(request):
    return _paginate(request,_owned_clients(request).prefetch_related("contacts","conversations","intelligence").order_by("-updated_at"),ClientSerializer)

@api_view(["POST"])
def sync_clients(request):
    count=0
    for lead in _owned_leads(request).iterator():
        if lead.company:
            sync_lead_client(lead); count+=1
    return Response({"synced":count,"clients":_owned_clients(request).count()})

@api_view(["GET"])
def client_detail(request,pk):
    client=_owned_clients(request).prefetch_related("contacts","conversations__messages","intelligence").filter(pk=pk).first()
    if not client: return Response({"detail":"Client not found."},status=404)
    return Response(ClientSerializer(client).data)

@api_view(["POST"])
@throttle_classes([AIThrottle])
def client_intelligence(request,pk):
    client=_owned_clients(request).filter(pk=pk).first()
    if not client: return Response({"detail":"Client not found."},status=404)
    intelligence=generate_client_intelligence(client)
    return Response({"client":ClientSerializer(client).data,"intelligence":ClientIntelligenceSerializer(intelligence).data})

@api_view(["GET"])
def meetings(request):
    return _paginate(request,Meeting.objects.filter(models.Q(lead__owner=request.user)|models.Q(client__owner=request.user)).select_related("client","lead","contact").order_by("-scheduled_at","-created_at"),MeetingSerializer)

@api_view(["POST"])
def create_meeting(request):
    lead=None
    if request.data.get("lead_id"):
        lead=_owned_lead(request, request.data["lead_id"])
        if not lead: return Response({"detail":"Lead not found."},status=404)
    client=None
    if request.data.get("client_id"):
        client=_owned_clients(request).filter(pk=request.data["client_id"]).first()
        if not client: return Response({"detail":"Client not found."},status=404)
    if lead and not client: client,_=sync_lead_client(lead)
    status_value=str(request.data.get("status") or "requested")
    if status_value not in {x[0] for x in Meeting.STATUS}: return Response({"detail":"Invalid meeting status."},status=400)
    contact_id=request.data.get("contact_id")
    if contact_id:
        contact=Contact.objects.filter(client__owner=request.user,pk=contact_id).first()
        if not contact: return Response({"detail":"Contact not found."},status=404)
        if client and contact.client_id!=client.id: return Response({"detail":"Contact does not belong to this client."},status=400)
    meeting=Meeting.objects.create(lead=lead,client=client,contact_id=contact_id,status="requested",scheduled_at=request.data.get("scheduled_at"),meeting_url=str(request.data.get("meeting_url") or ""),notes=str(request.data.get("notes") or ""),outcome=str(request.data.get("outcome") or ""),next_action=str(request.data.get("next_action") or ""))
    try:
        sync_meeting_context(meeting); apply_meeting_status(meeting,status_value)
    except ValueError as exc:
        meeting.delete()
        return Response({"detail":str(exc)},status=400)
    return Response(MeetingSerializer(meeting).data,status=201)

@api_view(["PATCH","PUT"])
def update_meeting(request,pk):
    meeting=Meeting.objects.filter(models.Q(lead__owner=request.user)|models.Q(client__owner=request.user),pk=pk).first()
    if not meeting: return Response({"detail":"Meeting not found."},status=404)
    allowed=["status","scheduled_at","meeting_url","notes","outcome","next_action","completed_at"]
    if "status" in request.data and str(request.data["status"]) not in {x[0] for x in Meeting.STATUS}: return Response({"detail":"Invalid meeting status."},status=400)
    requested_status=meeting.status
    if "status" in request.data: requested_status=str(request.data["status"])
    for field in allowed:
        if field != "status" and field in request.data: setattr(meeting,field,request.data[field])
    try:
        sync_meeting_context(meeting); apply_meeting_status(meeting,requested_status)
    except ValueError as exc:
        return Response({"detail":str(exc)},status=400)
    return Response(MeetingSerializer(meeting).data)

@api_view(["GET"])
def acquisition_events(request):
    return _paginate(request,AcquisitionEvent.objects.filter(lead__owner=request.user).select_related("lead").order_by("-occurred_at"),AcquisitionEventSerializer)

@api_view(["GET"])
def learning(request):
    refresh_learning(owner=request.user)
    return Response({"stats":LearningStatSerializer(LearningStat.objects.filter(owner=request.user)[:100],many=True).data})

@api_view(["POST"])
def refresh_learning_view(request):
    stats=refresh_learning(owner=request.user)
    return Response({"refreshed":len(stats),"stats":stats[:100]})


@api_view(["GET"])
def acquisition_queue(request):
    try: limit=min(max(int(request.query_params.get("limit",50)),1),100)
    except (TypeError,ValueError): return Response({"detail":"limit must be an integer."},status=400)
    return Response(AcquisitionOpportunitySerializer(build_queue(limit, owner=request.user),many=True).data)

@api_view(["GET"])
def acquisition_next_actions(request):
    rows=build_queue(20, owner=request.user)
    return Response([{"opportunity_id":x.id,"lead_id":x.lead_id,"action":x.recommended_action,"score":x.score,"reason":x.reason} for x in rows])

@api_view(["POST"])
def acquisition_action(request,pk):
    obj=AcquisitionOpportunity.objects.select_related("lead").filter(lead__owner=request.user,pk=pk).first()
    if not obj:return Response({"detail":"Opportunity not found."},status=404)
    action=str(request.data.get("action") or obj.recommended_action); mode=str(request.data.get("mode") or "approval_required")
    try: approved=_parse_bool(request.data.get("approved"),False)
    except ValueError as exc: return Response({"detail":str(exc),"executed":False},status=400)
    try:return Response(execute_action(obj,action,mode=mode,approved=approved))
    except ValueError as exc:return Response({"detail":str(exc),"executed":False},status=400)

@api_view(["POST"])
def acquisition_recalculate(request): return Response(recalculate_opportunities(owner=request.user))


@api_view(["GET"])
def outreach_strategy(request):
    return Response({"plans":OutreachPlanSerializer(build_outreach_plans(50, owner=request.user),many=True).data,"channels":channel_metrics(owner=request.user)})

@api_view(["POST"])
def outreach_plan(request):
    lead=_owned_lead(request, request.data.get("lead_id"))
    if not lead:return Response({"detail":"Lead not found."},status=404)
    try: plan=create_plan(lead,str(request.data.get("channel") or "") or None,str(request.data.get("variant") or "A"))
    except ValueError as exc:return Response({"detail":str(exc)},status=400)
    return Response(OutreachPlanSerializer(plan).data,status=201)

@api_view(["POST"])
def approve_outreach_plan(request,pk):
    plan=OutreachPlan.objects.select_related("lead").filter(lead__owner=request.user,pk=pk).first()
    if not plan:return Response({"detail":"Outreach plan not found."},status=404)
    try: return Response(OutreachPlanSerializer(mark_approved(plan)).data)
    except ValueError as exc:return Response({"detail":str(exc)},status=400)


@api_view(["GET"])
def revenue_dashboard(request): return Response({**revenue_metrics(owner=request.user),"optimization":optimization_report(owner=request.user)})

@api_view(["GET"])
def revenue_records(request): return _paginate(request,RevenueRecord.objects.filter(lead__owner=request.user).select_related("lead").all(),RevenueRecordSerializer)

@api_view(["POST"])
def revenue_record(request):
    lead=_owned_lead(request, request.data.get("lead_id"))
    if not lead:return Response({"detail":"Lead not found."},status=404)
    record=upsert_revenue(lead,request.data)
    return Response(RevenueRecordSerializer(record).data,status=201)
