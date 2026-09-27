from datetime import datetime, timedelta
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from .models import ActivityLog,DiscoveryDomainStat,DiscoveryQueryCache,DiscoverySearchStat,FollowUp,Lead,LeadAnalysis,Outreach,Reply,LearningStat
