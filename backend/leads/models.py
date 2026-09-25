from django.db import models

class Lead(models.Model):
    STATUS_CHOICES = [
        ("new", "New"),
        ("qualified", "Qualified"),
        ("proposal", "Proposal"),
        ("contacted", "Contacted"),
        ("replied", "Replied"),
        ("won", "Won"),
        ("lost", "Lost"),
        ("archived", "Archived"),
    ]
    LEAD_TYPE_CHOICES = [
        ("freelance", "Freelance"),
        ("direct", "Direct"),
        ("startup", "Startup"),
        ("other", "Other"),
    ]

    title = models.CharField(max_length=255)
    company = models.CharField(max_length=255, blank=True)
    description = models.TextField()
    source = models.CharField(max_length=100, default="mock")
    source_url = models.URLField(blank=True)
    lead_type = models.CharField(max_length=30, choices=LEAD_TYPE_CHOICES, default="freelance")
    budget_text = models.CharField(max_length=255, blank=True)
    technologies = models.JSONField(default=list, blank=True)
    contact_info = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default="new")
    discovered_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class LeadAnalysis(models.Model):
    lead = models.OneToOneField(Lead, on_delete=models.CASCADE, related_name="analysis")
    relevant = models.BooleanField(default=False)
    match_score = models.PositiveSmallIntegerField(default=0)
    service_match = models.CharField(max_length=100, blank=True)
    requirements = models.JSONField(default=list, blank=True)
    pain_points = models.JSONField(default=list, blank=True)
    recommended_approach = models.TextField(blank=True)
    matching_projects = models.JSONField(default=list, blank=True)
    confidence = models.PositiveSmallIntegerField(default=0)
    model = models.CharField(max_length=100, default="mock")
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now=True)


class Outreach(models.Model):
    CHANNELS = [("email", "Email"), ("platform", "Platform"), ("linkedin", "LinkedIn")]
    STATUS = [("draft", "Draft"), ("approved", "Approved"), ("sent", "Sent")]
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="outreach")
    channel = models.CharField(max_length=30, choices=CHANNELS, default="email")
    message = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS, default="draft")
    approved_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class FollowUp(models.Model):
    STATUS = [("draft", "Draft"), ("approved", "Approved"), ("sent", "Sent")]
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="followups")
    scheduled_at = models.DateTimeField()
    message = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS, default="draft")
    approved_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)


class ActivityLog(models.Model):
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, null=True, blank=True, related_name="activity")
    event_type = models.CharField(max_length=100)
    message = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
