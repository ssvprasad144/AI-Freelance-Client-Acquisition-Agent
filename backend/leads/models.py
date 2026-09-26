from django.db import models

class Lead(models.Model):
    STATUS=[("new","New"),("qualified","Qualified"),("proposal","Proposal"),("contacted","Contacted"),("replied","Replied"),("won","Won"),("lost","Lost"),("archived","Archived")]
    TYPE=[("freelance","Freelance"),("direct","Direct"),("startup","Startup"),("other","Other")]
    title=models.CharField(max_length=255); normalized_title=models.CharField(max_length=255,blank=True,db_index=True); normalized_url=models.CharField(max_length=500,blank=True,db_index=True)
    company=models.CharField(max_length=255,blank=True); description=models.TextField(); source=models.CharField(max_length=100,default="mock"); source_url=models.URLField(blank=True)
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
    lead=models.ForeignKey(Lead,on_delete=models.CASCADE,related_name="outreach"); channel=models.CharField(max_length=30,default="email"); message=models.TextField()
    status=models.CharField(max_length=20,default="draft"); approved_at=models.DateTimeField(null=True,blank=True); sent_at=models.DateTimeField(null=True,blank=True); created_at=models.DateTimeField(auto_now_add=True)

class FollowUp(models.Model):
    STATUS=[("draft","Draft"),("approved","Approved"),("due","Due"),("sent","Sent"),("cancelled","Cancelled")]
    lead=models.ForeignKey(Lead,on_delete=models.CASCADE,related_name="followups"); scheduled_at=models.DateTimeField(); message=models.TextField()
    status=models.CharField(max_length=20,choices=STATUS,default="draft"); approved_at=models.DateTimeField(null=True,blank=True); sent_at=models.DateTimeField(null=True,blank=True); created_at=models.DateTimeField(auto_now_add=True)

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
    created_at=models.DateTimeField(auto_now_add=True)
    updated_at=models.DateTimeField(auto_now=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=["profile_id","normalized_query"],name="unique_discovery_query_cache")]
        ordering=["searched_at","created_at"]

class ActivityLog(models.Model):
    lead=models.ForeignKey(Lead,on_delete=models.CASCADE,null=True,blank=True,related_name="activity"); event_type=models.CharField(max_length=100)
    message=models.TextField(); metadata=models.JSONField(default=dict,blank=True); created_at=models.DateTimeField(auto_now_add=True)
    class Meta: ordering=["-created_at"]
