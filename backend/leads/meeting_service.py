from django.utils import timezone
from .models import AcquisitionEvent, Meeting
from .client_service import sync_lead_client
def sync_meeting_context(meeting):
    lead=meeting.lead
    if lead and not meeting.client_id:
        client,contact=sync_lead_client(lead)
        meeting.client=client; meeting.contact=meeting.contact or contact
        meeting.save(update_fields=["client","contact","updated_at"])
    return meeting
def record_meeting_event(meeting,event_type):
    if meeting.lead_id:
        AcquisitionEvent.objects.create(lead=meeting.lead,event_type=event_type,source=meeting.lead.source,profile_id=meeting.lead.discovery_profile,strategy_id=meeting.lead.discovery_strategy,query=meeting.lead.discovery_query,metadata={"meeting_id":meeting.id})
def apply_meeting_status(meeting,new_status):
    meeting.status=new_status
    if new_status=="completed" and not meeting.completed_at: meeting.completed_at=timezone.now()
    meeting.save()
    mapping={"requested":"meeting_requested","scheduled":"meeting_scheduled","completed":"meeting_completed"}
    if new_status in mapping: record_meeting_event(meeting,mapping[new_status])
    if new_status=="completed" and meeting.lead and meeting.lead.status=="replied":
        meeting.lead.status="contacted"; meeting.lead.save(update_fields=["status","updated_at"])
    return meeting
