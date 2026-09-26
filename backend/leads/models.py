from django.db import models

class Lead(models.Model):
    STATUS=[("new","New"),("qualified","Qualified"),("proposal","Proposal"),("contacted","Contacted"),("replied","Replied"),("won","Won"),("lost","Lost"),("archived","Archived")]
    TYPE=[("freelance","Freelance"),("direct","Direct"),("startup","Startup"),("other","Other")]
    title=models.CharField(max_length=255); normalized_title=models.CharField(max_length=255,blank=True,db_index=True); normalized_url=models.CharField(max_length=500,blank=True,db_index=True)
    company=models.CharField(max_length=255,blank=True); description=models.TextField(); source=models.CharField(max_length=100,default="mock"); source_url=models.URLField(blank=True); action_url=models.URLField(blank=True)
    lead_type=models.CharField(max_length=30,choices=TYPE,default="freelance"); budget_text=models.CharField(max_length=255,blank=True)
    technologies=models.JSONField(default=list,blank=True); contact_info=models.JSONField(default=dict,blank=True); status=models.CharField(max_length=30,choices=STATUS,default="new")
    discovered_at=models.DateTimeField(null=True,blank=True); posted_at=models.DateTimeField(null=True,blank=True); expires_at=models.DateTimeField(null=True,blank=True); last_verified_at=models.DateTimeField(null=True,blank=True)
    created_at=models.DateTimeField(auto_now_add=True); updated_at=models.DateTimeField(auto_now=True)
    class Meta: ordering=["-created_at"]
    def __str__(self): return self.title

class LeadAnalysis(models.Model):
    lead=models.OneToOneField(Lead,on_delete=models.CASCADE,related_name="analysis"); relevant=models.BooleanField(default=False); match_score=models.PositiveSmallIntegerField(default=0)
    service_match=models.CharField(max_length=100,blank=True); requirements=models.JSONField(default=list,blank=True); pain_points=models.JSONField(default=list,blank=True)
    recommended_approach=models.TextField(blank=True); matching_projects=models.JSONField(default=list,blank=True); confidence=models.PositiveSmallIntegerField(default=0)
    model=models.CharField(max_length=100,default="mock"); input_tokens=models.PositiveIntegerField(default=0); output_tokens=models.PositiveIntegerField(default=0); created_at=models.DateTimeField(auto_now=True)

class Outreach(models.Model):
    lead=models.ForeignKey(Lead,on_delete=models.CASCADE,related_name="outreach"); channel=models.CharField(max_length=30,default="email"); medium=models.CharField(max_length=40,default="email",db_index=True); action_type=models.CharField(max_length=50,default="send_email"); message=models.TextField()
    destination_url=models.URLField(blank=True); status=models.CharField(max_length=20,default="draft"); approved_at=models.DateTimeField(null=True,blank=True); opened_at=models.DateTimeField(null=True,blank=True); submitted_at=models.DateTimeField(null=True,blank=True); sent_at=models.DateTimeField(null=True,blank=True); created_at=models.DateTimeField(auto_now_add=True)

class FollowUp(models.Model):
    STATUS=[("draft","Draft"),("approved","Approved"),("due","Due"),("sent","Sent"),("cancelled","Cancelled")]
    lead=models.ForeignKey(Lead,on_delete=models.CASCADE,related_name="followups"); scheduled_at=models.DateTimeField(); message=models.TextField()
    status=models.CharField(max_length=20,default="draft"); approved_at=models.DateTimeField(null=True,blank=True); sent_at=models.DateTimeField(null=True,blank=True); created_at=models.DateTimeField(auto_now_add=True)

class Reply(models.Model):
    lead=models.ForeignKey(Lead,on_delete=models.CASCADE,related_name="replies")
    channel=models.CharField(max_length=30,default="email")
    message=models.TextField()
    sentiment=models.CharField(max_length=30,blank=True)
    intent=models.CharField(max_length=50,blank=True)
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
