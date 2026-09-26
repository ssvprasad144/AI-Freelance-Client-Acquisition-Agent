from rest_framework import serializers
from .models import ActivityLog,FollowUp,FollowUpSequence,Lead,LeadAnalysis,Outreach,Proposal,ProposalVersion,Reply,Client,Contact,Conversation,ConversationMessage,ClientIntelligence,Meeting,AcquisitionEvent,LearningStat

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


class ProposalVersionSerializer(serializers.ModelSerializer):
    class Meta: model=ProposalVersion; fields="__all__"

class ProposalSerializer(serializers.ModelSerializer):
    versions=ProposalVersionSerializer(many=True,read_only=True)
    lead_title=serializers.CharField(source="lead.title",read_only=True)
    class Meta: model=Proposal; fields="__all__"

class FollowUpSequenceSerializer(serializers.ModelSerializer):
    followups=serializers.PrimaryKeyRelatedField(many=True,read_only=True)
    class Meta: model=FollowUpSequence; fields="__all__"


class ContactSerializer(serializers.ModelSerializer):
    class Meta: model=Contact; fields="__all__"

class ClientIntelligenceSerializer(serializers.ModelSerializer):
    class Meta: model=ClientIntelligence; fields="__all__"

class ConversationMessageSerializer(serializers.ModelSerializer):
    class Meta: model=ConversationMessage; fields="__all__"

class ConversationSerializer(serializers.ModelSerializer):
    messages=ConversationMessageSerializer(many=True,read_only=True)
    class Meta: model=Conversation; fields="__all__"

class ClientSerializer(serializers.ModelSerializer):
    contacts=ContactSerializer(many=True,read_only=True)
    conversations=ConversationSerializer(many=True,read_only=True)
    intelligence=ClientIntelligenceSerializer(read_only=True)
    lead_count=serializers.SerializerMethodField()
    def get_lead_count(self,obj): return obj.leads.count()
    class Meta: model=Client; fields="__all__"

class MeetingSerializer(serializers.ModelSerializer):
    client_company=serializers.CharField(source="client.company",read_only=True)
    lead_title=serializers.CharField(source="lead.title",read_only=True)
    class Meta: model=Meeting; fields="__all__"

class AcquisitionEventSerializer(serializers.ModelSerializer):
    class Meta: model=AcquisitionEvent; fields="__all__"

class LearningStatSerializer(serializers.ModelSerializer):
    class Meta: model=LearningStat; fields="__all__"
