from django.contrib import admin
from .models import ActivityLog, FollowUp, Lead, LeadAnalysis, Outreach

@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ("title", "company", "source", "lead_type", "status", "created_at")
    list_filter = ("status", "lead_type", "source")
    search_fields = ("title", "company", "description")

admin.site.register(LeadAnalysis)
admin.site.register(Outreach)
admin.site.register(FollowUp)
admin.site.register(ActivityLog)
