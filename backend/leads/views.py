from django.db.models import Count
from django.http import JsonResponse
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .ai_service import analyze_lead, generate_proposal
from .models import ActivityLog, Lead, LeadAnalysis, Outreach
from .serializers import ActivityLogSerializer, LeadSerializer

def health(request):
    return JsonResponse({"status": "ok", "service": "ai-freelance-client-acquisition-agent"})

class LeadViewSet(viewsets.ModelViewSet):
    queryset = Lead.objects.all().prefetch_related("analysis")
    serializer_class = LeadSerializer

    @action(detail=True, methods=["post"])
    def analyze(self, request, pk=None):
        lead = self.get_object()
        data = analyze_lead(lead)
        analysis, _ = LeadAnalysis.objects.update_or_create(lead=lead, defaults=data)
        if analysis.relevant and lead.status == "new":
            lead.status = "qualified"
            lead.save(update_fields=["status", "updated_at"])
        ActivityLog.objects.create(
            lead=lead,
            event_type="lead.analyzed",
            message=f"Lead analyzed with score {analysis.match_score}.",
            metadata={"model": analysis.model, "match_score": analysis.match_score},
        )
        return Response(LeadSerializer(lead).data)

    @action(detail=True, methods=["post"])
    def proposal(self, request, pk=None):
        lead = self.get_object()
        analysis = getattr(lead, "analysis", None)
        if not analysis:
            return Response({"detail": "Analyze the lead first."}, status=status.HTTP_400_BAD_REQUEST)
        message = generate_proposal(lead, analysis)
        outreach = Outreach.objects.create(
            lead=lead,
            channel="email",
            message=message,
            status="draft",
        )
        lead.status = "proposal"
        lead.save(update_fields=["status", "updated_at"])
        ActivityLog.objects.create(
            lead=lead,
            event_type="proposal.generated",
            message="Proposal draft generated. No message was sent.",
            metadata={"outreach_id": outreach.id},
        )
        return Response({"outreach_id": outreach.id, "status": outreach.status, "message": outreach.message})

def dashboard(request):
    return JsonResponse({
        "opportunities": Lead.objects.exclude(status="archived").count(),
        "qualified": Lead.objects.filter(status="qualified").count(),
        "proposals": Lead.objects.filter(status="proposal").count(),
        "replies": Lead.objects.filter(status="replied").count(),
        "high_match": LeadAnalysis.objects.filter(match_score__gte=80).count(),
    })

def activity(request):
    return JsonResponse({
        "items": ActivityLogSerializer(ActivityLog.objects.all()[:50], many=True).data
    })
