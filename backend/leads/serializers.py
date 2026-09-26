from rest_framework import serializers
from .models import ActivityLog,FollowUp,Lead,LeadAnalysis,Outreach,Reply

class LeadAnalysisSerializer(serializers.ModelSerializer):
    class Meta: model=LeadAnalysis; fields="__all__"

class LeadSerializer(serializers.ModelSerializer):
    analysis=LeadAnalysisSerializer(read_only=True)
    class Meta: model=Lead; fields="__all__"

class OutreachSerializer(serializers.ModelSerializer):
    lead_title=serializers.CharField(source="lead.title",read_only=True)
    lead_source=serializers.CharField(source="lead.source",read_only=True)
    class Meta: model=Outreach; fields="__all__"

class FollowUpSerializer(serializers.ModelSerializer):
    lead_title=serializers.CharField(source="lead.title",read_only=True)
    class Meta: model=FollowUp; fields="__all__"

class ReplySerializer(serializers.ModelSerializer):
    lead_title=serializers.CharField(source="lead.title",read_only=True)
    class Meta: model=Reply; fields="__all__"

class ActivityLogSerializer(serializers.ModelSerializer):
    class Meta: model=ActivityLog; fields="__all__"
