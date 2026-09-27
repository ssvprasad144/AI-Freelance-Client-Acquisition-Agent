from rest_framework import serializers
from .models import ActivityLog,FollowUp,FollowUpSequence,Lead,LeadAnalysis,Outreach,Proposal,ProposalVersion,Reply,Client,Contact,Conversation,ConversationMessage,ClientIntelligence,Meeting,AcquisitionEvent,LearningStat,AcquisitionOpportunity,OutreachPlan,RevenueRecord
from .data_quality import normalize_url, validate_discovered_email

class LeadAnalysisSerializer(serializers.ModelSerializer):
    class Meta: model=LeadAnalysis; fields="__all__"

class LeadSerializer(serializers.ModelSerializer):
    analysis=LeadAnalysisSerializer(read_only=True)
    evidence=serializers.PrimaryKeyRelatedField(many=True,read_only=True)
    class Meta: model=Lead; fields="__all__"
    def validate_source_url(self,value): return normalize_url(value) if value else value
    def validate_action_url(self,value): return normalize_url(value) if value else value
    def validate_company_website(self,value): return normalize_url(value) if value else value
    def validate(self,attrs):
        info=attrs.get("contact_info")
        if info is not None:
            if not isinstance(info,dict): raise serializers.ValidationError({"contact_info":"Must be an object."})
            info=dict(info)
            if info.get("email"):
                try: info["email"]=validate_discovered_email(info["email"])
                except ValueError as exc: raise serializers.ValidationError({"contact_info":{"email":str(exc)}}) from exc
            for key in ("profile_url","linkedin"):
                if info.get(key):
                    try: info[key]=normalize_url(info[key])
                    except ValueError as exc: raise serializers.ValidationError({"contact_info":{key:str(exc)}}) from exc
            attrs["contact_info"]=info
        return attrs

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


class AcquisitionOpportunitySerializer(serializers.ModelSerializer):
    lead_title=serializers.CharField(source="lead.title",read_only=True)
    lead_status=serializers.CharField(source="lead.status",read_only=True)
    class Meta: model=AcquisitionOpportunity; fields="__all__"


class OutreachPlanSerializer(serializers.ModelSerializer):
    lead_title=serializers.CharField(source="lead.title",read_only=True)
    class Meta: model=OutreachPlan; fields="__all__"


class RevenueRecordSerializer(serializers.ModelSerializer):
    lead_title=serializers.CharField(source="lead.title",read_only=True)
    class Meta: model=RevenueRecord; fields="__all__"
