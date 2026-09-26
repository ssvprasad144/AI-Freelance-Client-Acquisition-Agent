from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from .models import Lead, RevenueRecord
from .revenue_intelligence import upsert_revenue, expected_value, revenue_metrics, attribution_for

class Phase18Tests(TestCase):
    def setUp(self):
        self.api=APIClient(); user=get_user_model().objects.create_user(username="p18",password="pass123"); self.api.force_authenticate(user)
        self.lead=Lead.objects.create(title="AI build",description="Build AI",source="direct",discovery_strategy="direct-web",status="qualified")
    def test_expected_value_and_upsert(self):
        record=upsert_revenue(self.lead,{"quoted_value":1000,"probability":50,"currency":"USD","ai_cost":2})
        self.assertEqual(float(record.expected_value),500)
        self.assertEqual(RevenueRecord.objects.count(),1)
    def test_attribution_and_expected_value_update(self):
        record=upsert_revenue(self.lead,{"estimated_value":2000,"probability":25,"currency":"USD"})
        self.assertEqual(record.strategy_id,"direct-web")
        self.assertEqual(float(record.expected_value),500)
        record=upsert_revenue(self.lead,{"won_value":2000,"probability":100,"currency":"USD"})
        self.assertEqual(float(record.expected_value),2000)

    def test_revenue_api(self):
        upsert_revenue(self.lead,{"won_value":1000,"probability":100,"currency":"USD","search_cost":10})
        response=self.api.get("/api/revenue/")
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.data["revenue"],1000.0)
