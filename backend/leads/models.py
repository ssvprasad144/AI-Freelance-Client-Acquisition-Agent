from django.db import models
from django.utils import timezone

class Lead(models.Model):
    STATUS=[("new","New"),("qualified","Qualified"),("proposal","Proposal"),("contacted","Contacted"),("replied","Replied"),("won","Won"),("lost","Lost"),("archived","Archived")]
    TYPE=[("freelance","Freelance"),("direct","Direct"),("startup","Startup"),("other","Other")]
    title=models.CharField(max_length=255); normalized_title=models.CharField(max_length=255,blank=True,db_index=True); normalized_url=models.CharField(max_length=500,blank=True,db_index=True)
    company=models.CharField(max_length=255,blank=True); description=models.TextField(); source=models.CharField(max_length=100,default="mock"); source_url=models.URLField(blank=True); action_url=models.URLField(blank=True)
    lead_type=models.CharField(max_length=30,choices=TYPE,default="freelance"); budget_text=models.CharField(max_length=255,blank=True)
    technologies=models.JSONField(default=list,blank=True); contact_info=models.JSONField(default=dict,blank=True); status=models.CharField(max_length=30,choices=STATUS,default="new")
    client=models.ForeignKey("Client",on_delete=models.SET_NULL,null=True,blank=True,related_name="leads"); contact=models.ForeignKey("Contact",on_delete=models.SET_NULL,null=True,blank=True,related_name="leads")
    discovery_profile=models.CharField(max_length=100,blank=True,db_index=True); discovery_strategy=models.CharField(max_length=100,blank=True,db_index=True); discovery_query=models.CharField(max_length=1000,blank=True)
    discovered_at=models.DateTimeField(null=True,blank=True); posted_at=models.DateTimeField(null=True,blank=True); expires_at=models.DateTimeField(null=True,blank=True); last_verified_at=models.DateTimeField(null=True,blank=True)
    created_at=models.DateTimeField(auto_now_add=True); updated_at=models.DateTimeField(auto_now=True)
    class Meta: ordering=["-created_at"]
    def __str__(self): return self.title

class LeadAnalysis(models.Model):
    lead=models.OneToOneField(Lead,on_delete=models.CASCADE,related_name="analysis"); relevant=models.BooleanField(default=False); match_score=models.PositiveSmallIntegerField(default=0)
    service_match=models.CharField(max_length=100,blank=True); requirements=models.JSONField(default=list,blank=True); pain_points=models.JSONField(default=list,blank=True)
    recommended_approach=models.TextField(blank=True); matching_projects=models.JSONField(default=list,blank=True); confidence=models.PositiveSmallIntegerField(default=0)
    model=models.CharField(max_length=100,default="mock"); input_tokens=models.PositiveIntegerField(default=0); output_tokens=models.PositiveIntegerField(default=0); created_at=models.DateTimeField(auto_now=True)

class Proposal(models.Model):
    STATUS=[("draft","Draft"),("approved","Approved"),("archived","Archived")]
    lead=models.ForeignKey(Lead,on_delete=models.CASCADE,related_name="proposals")
    status=models.CharField(max_length=20,choices=STATUS,default="draft",db_index=True)
    current_version=models.PositiveIntegerField(default=1)
    delivery_medium=models.CharField(max_length=40,blank=True)
    approved_at=models.DateTimeField(null=True,blank=True)
    created_at=models.DateTimeField(auto_now_add=True)
    updated_at=models.DateTimeField(auto_now=True)
    class Meta: ordering=["-created_at"]

class ProposalVersion(models.Model):
    proposal=models.ForeignKey(Proposal,on_delete=models.CASCADE,related_name="versions")
    version_number=models.PositiveIntegerField()
    content=models.TextField()
    source=models.CharField(max_length=20,default="ai")
    instruction=models.TextField(blank=True)
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=["proposal","version_number"],name="unique_proposal_version")]
        ordering=["-version_number"]

class Outreach(models.Model):
    lead=models.ForeignKey(Lead,on_delete=models.CASCADE,related_name="outreach"); proposal=models.ForeignKey(Proposal,on_delete=models.SET_NULL,null=True,blank=True,related_name="outreach")
    channel=models.CharField(max_length=30,default="email"); medium=models.CharField(max_length=40,default="email",db_index=True); action_type=models.CharField(max_length=50,default="send_email"); message=models.TextField()
    destination_url=models.URLField(blank=True); status=models.CharField(max_length=20,default="draft"); approved_at=models.DateTimeField(null=True,blank=True); opened_at=models.DateTimeField(null=True,blank=True); submitted_at=models.DateTimeField(null=True,blank=True); sent_at=models.DateTimeField(null=True,blank=True); created_at=models.DateTimeField(auto_now_add=True)

class FollowUpSequence(models.Model):
    STATUS=[("active","Active"),("paused","Paused"),("completed","Completed"),("cancelled","Cancelled")]
    lead=models.ForeignKey(Lead,on_delete=models.CASCADE,related_name="followup_sequences")
    name=models.CharField(max_length=120,default="Default follow-up")
    status=models.CharField(max_length=20,choices=STATUS,default="active")
    max_steps=models.PositiveSmallIntegerField(default=3)
    stop_on_reply=models.BooleanField(default=True)
    stop_on_terminal_status=models.BooleanField(default=True)
    current_step=models.PositiveSmallIntegerField(default=0)
    medium=models.CharField(max_length=40,default="email")
    action_type=models.CharField(max_length=50,default="send_email")
    destination_url=models.URLField(blank=True)
    delays_days=models.JSONField(default=list,blank=True)
    created_at=models.DateTimeField(auto_now_add=True)
    updated_at=models.DateTimeField(auto_now=True)

class FollowUp(models.Model):
    STATUS=[("draft","Draft"),("approved","Approved"),("due","Due"),("sent","Sent"),("cancelled","Cancelled")]
    lead=models.ForeignKey(Lead,on_delete=models.CASCADE,related_name="followups"); sequence=models.ForeignKey(FollowUpSequence,on_delete=models.SET_NULL,null=True,blank=True,related_name="followups")
    step_number=models.PositiveSmallIntegerField(default=1)
    medium=models.CharField(max_length=40,default="email")
    action_type=models.CharField(max_length=50,default="send_email")
    destination_url=models.URLField(blank=True)
    scheduled_at=models.DateTimeField(); message=models.TextField()
    status=models.CharField(max_length=20,default="draft"); approved_at=models.DateTimeField(null=True,blank=True); sent_at=models.DateTimeField(null=True,blank=True); created_at=models.DateTimeField(auto_now_add=True)

class Reply(models.Model):
    lead=models.ForeignKey(Lead,on_delete=models.CASCADE,related_name="replies")
    channel=models.CharField(max_length=30,default="email")
    message=models.TextField()
    sentiment=models.CharField(max_length=30,blank=True)
    intent=models.CharField(max_length=50,blank=True)
    urgency=models.CharField(max_length=20,blank=True)
    confidence=models.PositiveSmallIntegerField(default=0)
    extracted_questions=models.JSONField(default=list,blank=True)
    recommended_action=models.TextField(blank=True)
    suggested_response=models.TextField(blank=True)
    next_action=models.CharField(max_length=50,blank=True)
    created_at=models.DateTimeField(auto_now_add=True)

class DiscoveryQueryCache(models.Model):
    query=models.CharField(max_length=1000)
    normalized_query=models.CharField(max_length=1000,db_index=True)
    profile_id=models.CharField(max_length=100,default="custom",db_index=True)
    searched_at=models.DateTimeField(null=True,blank=True,db_index=True)
    result_count=models.PositiveIntegerField(default=0)
    query_family=models.CharField(max_length=120,default="general",db_index=True)
    query_signature=models.CharField(max_length=64,default="",db_index=True)
    result_payload=models.JSONField(default=list,blank=True)
    source_domains=models.JSONField(default=list,blank=True)
    created_at=models.DateTimeField(auto_now_add=True)
    updated_at=models.DateTimeField(auto_now=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=["profile_id","normalized_query"],name="unique_discovery_query_cache")]
        ordering=["searched_at","created_at"]

class DiscoverySearchStat(models.Model):
    profile_id=models.CharField(max_length=100,db_index=True)
    strategy_id=models.CharField(max_length=100,default="general-web",db_index=True)
    query=models.CharField(max_length=1000)
    normalized_query=models.CharField(max_length=1000,db_index=True)
    source=models.CharField(max_length=100,default="web_search",db_index=True)
    search_date=models.DateField(db_index=True)
    raw_results=models.PositiveIntegerField(default=0)
    valid_results=models.PositiveIntegerField(default=0)
    unique_results=models.PositiveIntegerField(default=0)
    scored_candidates=models.PositiveIntegerField(default=0)
    crawled_candidates=models.PositiveIntegerField(default=0)
    newly_created_leads=models.PositiveIntegerField(default=0)
    duplicates=models.PositiveIntegerField(default=0)
    locally_filtered=models.PositiveIntegerField(default=0)
    ai_calls=models.PositiveIntegerField(default=0)
    analyzed=models.PositiveIntegerField(default=0)
    qualified=models.PositiveIntegerField(default=0)
    replied=models.PositiveIntegerField(default=0)
    won=models.PositiveIntegerField(default=0)
    query_family=models.CharField(max_length=120,default="general",db_index=True)
    query_variant=models.CharField(max_length=120,default="base",db_index=True)
    source_domains=models.JSONField(default=list,blank=True)
    context_size=models.CharField(max_length=20,default="low")
    created_at=models.DateTimeField(auto_now_add=True)
    updated_at=models.DateTimeField(auto_now=True)
    class Meta:
        ordering=["-search_date","-created_at"]
        indexes=[models.Index(fields=["profile_id","search_date"]),models.Index(fields=["source","search_date"])]

class ActivityLog(models.Model):
    lead=models.ForeignKey(Lead,on_delete=models.CASCADE,null=True,blank=True,related_name="activity"); event_type=models.CharField(max_length=100)
    message=models.TextField(); metadata=models.JSONField(default=dict,blank=True); created_at=models.DateTimeField(auto_now_add=True)
    class Meta: ordering=["-created_at"]


class DiscoveryDomainStat(models.Model):
    domain=models.CharField(max_length=255,unique=True)
    searches=models.PositiveIntegerField(default=0)
    results=models.PositiveIntegerField(default=0)
    qualified=models.PositiveIntegerField(default=0)
    replied=models.PositiveIntegerField(default=0)
    won=models.PositiveIntegerField(default=0)
    last_seen_at=models.DateTimeField(null=True,blank=True)
    blocked_until=models.DateTimeField(null=True,blank=True)
    created_at=models.DateTimeField(auto_now_add=True)
    updated_at=models.DateTimeField(auto_now=True)
    class Meta:
        ordering=["-qualified","-results"]


class Client(models.Model):
    STATUS=[("active","Active"),("prospect","Prospect"),("won","Won"),("lost","Lost"),("archived","Archived")]
    company=models.CharField(max_length=255)
    normalized_company=models.CharField(max_length=255,unique=True,db_index=True)
    domain=models.CharField(max_length=255,blank=True,db_index=True)
    industry=models.CharField(max_length=120,blank=True)
    notes=models.TextField(blank=True)
    status=models.CharField(max_length=20,choices=STATUS,default="prospect",db_index=True)
    created_at=models.DateTimeField(auto_now_add=True)
    updated_at=models.DateTimeField(auto_now=True)
    class Meta: ordering=["-updated_at"]
    def __str__(self): return self.company

class Contact(models.Model):
    client=models.ForeignKey(Client,on_delete=models.CASCADE,related_name="contacts")
    name=models.CharField(max_length=255,blank=True)
    email=models.EmailField(blank=True)
    profile_url=models.URLField(blank=True)
    role=models.CharField(max_length=120,blank=True)
    metadata=models.JSONField(default=dict,blank=True)
    created_at=models.DateTimeField(auto_now_add=True)
    updated_at=models.DateTimeField(auto_now=True)

class Conversation(models.Model):
    STATUS=[("open","Open"),("waiting","Waiting"),("closed","Closed")]
    client=models.ForeignKey(Client,on_delete=models.CASCADE,related_name="conversations")
    contact=models.ForeignKey(Contact,on_delete=models.SET_NULL,null=True,blank=True,related_name="conversations")
    lead=models.ForeignKey(Lead,on_delete=models.SET_NULL,null=True,blank=True,related_name="conversations")
    channel=models.CharField(max_length=40,default="email")
    status=models.CharField(max_length=20,choices=STATUS,default="open")
    last_interaction_at=models.DateTimeField(null=True,blank=True)
    created_at=models.DateTimeField(auto_now_add=True)
    updated_at=models.DateTimeField(auto_now=True)

class ConversationMessage(models.Model):
    DIRECTION=[("inbound","Inbound"),("outbound","Outbound")]
    conversation=models.ForeignKey(Conversation,on_delete=models.CASCADE,related_name="messages")
    direction=models.CharField(max_length=20,choices=DIRECTION)
    message=models.TextField()
    occurred_at=models.DateTimeField(default=timezone.now)
    metadata=models.JSONField(default=dict,blank=True)

class ClientIntelligence(models.Model):
    client=models.OneToOneField(Client,on_delete=models.CASCADE,related_name="intelligence")
    summary=models.TextField(blank=True)
    communication_style=models.CharField(max_length=120,blank=True)
    preferences=models.JSONField(default=list,blank=True)
    objections=models.JSONField(default=list,blank=True)
    recommended_approach=models.TextField(blank=True)
    confidence=models.PositiveSmallIntegerField(default=0)
    model=models.CharField(max_length=100,default="deterministic")
    generated_at=models.DateTimeField(auto_now=True)

class Meeting(models.Model):
    STATUS=[("requested","Requested"),("scheduled","Scheduled"),("completed","Completed"),("cancelled","Cancelled"),("no_show","No-show")]
    lead=models.ForeignKey(Lead,on_delete=models.SET_NULL,null=True,blank=True,related_name="meetings")
    client=models.ForeignKey(Client,on_delete=models.SET_NULL,null=True,blank=True,related_name="meetings")
    contact=models.ForeignKey(Contact,on_delete=models.SET_NULL,null=True,blank=True,related_name="meetings")
    status=models.CharField(max_length=20,choices=STATUS,default="requested",db_index=True)
    scheduled_at=models.DateTimeField(null=True,blank=True)
    completed_at=models.DateTimeField(null=True,blank=True)
    meeting_url=models.URLField(blank=True)
    notes=models.TextField(blank=True)
    outcome=models.TextField(blank=True)
    next_action=models.CharField(max_length=120,blank=True)
    created_at=models.DateTimeField(auto_now_add=True)
    updated_at=models.DateTimeField(auto_now=True)

class AcquisitionEvent(models.Model):
    lead=models.ForeignKey(Lead,on_delete=models.CASCADE,related_name="acquisition_events")
    event_type=models.CharField(max_length=40,db_index=True)
    source=models.CharField(max_length=100,blank=True,db_index=True)
    profile_id=models.CharField(max_length=100,blank=True,db_index=True)
    strategy_id=models.CharField(max_length=100,blank=True,db_index=True)
    query=models.CharField(max_length=1000,blank=True)
    domain=models.CharField(max_length=255,blank=True,db_index=True)
    metadata=models.JSONField(default=dict,blank=True)
    occurred_at=models.DateTimeField(default=timezone.now,db_index=True)

class LearningStat(models.Model):
    DIMENSIONS=[("source","Source"),("profile","Profile"),("strategy","Strategy"),("domain","Domain"),("lead_type","Lead type"),("query","Query")]
    dimension=models.CharField(max_length=30,choices=DIMENSIONS,db_index=True)
    key=models.CharField(max_length=1000,db_index=True)
    attempts=models.PositiveIntegerField(default=0)
    qualified=models.PositiveIntegerField(default=0)
    proposals=models.PositiveIntegerField(default=0)
    sent=models.PositiveIntegerField(default=0)
    replies=models.PositiveIntegerField(default=0)
    meetings=models.PositiveIntegerField(default=0)
    wins=models.PositiveIntegerField(default=0)
    losses=models.PositiveIntegerField(default=0)
    reward=models.FloatField(default=0)
    updated_at=models.DateTimeField(auto_now=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=["dimension","key"],name="unique_learning_dimension_key")]
        ordering=["-reward","-updated_at"]


class AcquisitionOpportunity(models.Model):
    lead=models.OneToOneField(Lead,on_delete=models.CASCADE,related_name="opportunity")
    score=models.FloatField(default=0,db_index=True)
    stage=models.CharField(max_length=30,default="new",db_index=True)
    recommended_action=models.CharField(max_length=60,default="review",db_index=True)
    action_category=models.CharField(max_length=60,default="")
    reason=models.TextField(blank=True)
    status=models.CharField(max_length=30,default="ready",db_index=True)
    executed_at=models.DateTimeField(null=True,blank=True)
    created_at=models.DateTimeField(auto_now_add=True)
    updated_at=models.DateTimeField(auto_now=True)
    class Meta: ordering=["-score","-updated_at"]
