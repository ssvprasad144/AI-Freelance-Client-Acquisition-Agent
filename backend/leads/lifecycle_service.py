from django.db.models import Q
from .models import Lead, Client, FollowUp, Outreach, Proposal, RevenueRecord, AcquisitionOpportunity, Meeting

TERMINAL_STATUSES={"won","lost","archived"}
ACTIVE_FOLLOWUP_STATUSES={"draft","approved","due","sending"}
ACTIVE_OUTREACH_STATUSES={"draft","approved","opened","sending"}


def validate_pipeline_invariants(lead):
    """Return deterministic lifecycle violations for a single lead."""
    violations=[]
    if lead.owner_id is None:
        violations.append("lead_owner_missing")
    if lead.client_id and lead.client and lead.client.owner_id != lead.owner_id:
        violations.append("client_owner_mismatch")
    if lead.contact_id and not lead.client_id:
        violations.append("contact_without_client")
    if lead.contact_id and lead.contact and lead.client_id and lead.contact.client_id != lead.client_id:
        violations.append("contact_client_mismatch")
    if lead.status in TERMINAL_STATUSES:
        if lead.followups.filter(status__in=ACTIVE_FOLLOWUP_STATUSES).exists():
            violations.append("terminal_lead_has_active_followup")
        if lead.outreach.filter(status__in=ACTIVE_OUTREACH_STATUSES).exists():
            violations.append("terminal_lead_has_active_outreach")
    if lead.status == "won" and not lead.revenue.exists():
        violations.append("won_lead_missing_revenue_record")
    if lead.status in {"proposal","contacted","replied","won"} and not lead.proposals.exists():
        violations.append("advanced_lead_missing_proposal")
    if lead.status in {"contacted","replied","won"} and not lead.outreach.filter(status__in={"sent","submitted"}).exists() and not lead.replies.exists():
        violations.append("contacted_lead_missing_outreach")
    opportunity=AcquisitionOpportunity.objects.filter(lead=lead).first()
    if not opportunity and lead.status not in TERMINAL_STATUSES:
        violations.append("active_lead_missing_opportunity")
    return violations


def validate_workspace(owner):
    """Validate owner isolation and lifecycle invariants for the single-owner workspace."""
    report={"owner_id":owner.id,"leads":0,"clients":0,"violations":[]}
    leads=Lead.objects.filter(owner=owner).select_related("client","contact").prefetch_related("followups","outreach","proposals","revenue")
    report["leads"]=leads.count()
    report["clients"]=Client.objects.filter(owner=owner).count()
    for lead in leads:
        for code in validate_pipeline_invariants(lead):
            report["violations"].append({"lead_id":lead.id,"code":code})
    for client in Client.objects.filter(owner=owner):
        if client.leads.exclude(owner=owner).exists():
            report["violations"].append({"client_id":client.id,"code":"client_has_cross_owner_lead"})
        for contact in client.contacts.all():
            if contact.leads.filter(client__isnull=True).exists():
                report["violations"].append({"client_id":client.id,"contact_id":contact.id,"code":"contact_lead_without_client"})
            if contact.leads.exclude(client=client).exists():
                report["violations"].append({"client_id":client.id,"contact_id":contact.id,"code":"contact_lead_client_mismatch"})
        for meeting in Meeting.objects.filter(Q(lead__client=client)|Q(client=client)):
            if meeting.lead_id and meeting.client_id and meeting.lead.client_id != meeting.client_id:
                report["violations"].append({"client_id":client.id,"meeting_id":meeting.id,"code":"meeting_lead_client_mismatch"})
            if meeting.contact_id and meeting.contact.client_id != client.id:
                report["violations"].append({"client_id":client.id,"meeting_id":meeting.id,"code":"meeting_contact_client_mismatch"})
    orphan_clients=Client.objects.filter(owner__isnull=True).count()
    orphan_leads=Lead.objects.filter(owner__isnull=True).count()
    report["ownerless_records"]={"leads":orphan_leads,"clients":orphan_clients}
    report["ok"]=not report["violations"] and not orphan_leads and not orphan_clients
    return report
