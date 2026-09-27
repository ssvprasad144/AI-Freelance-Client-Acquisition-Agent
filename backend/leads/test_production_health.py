from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import ActivityLog


class ProductionHealthTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_health_reports_database_and_unknown_cron_state(self):
        response = self.client.get("/api/health/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "healthy")
        self.assertEqual(response.data["database"], "ok")
        self.assertEqual(response.data["workers"]["discovery_cron"]["status"], "unknown")

    def test_health_fails_when_discovery_cron_is_stale(self):
        old = timezone.now() - timedelta(hours=2)
        ActivityLog.objects.create(event_type="cron.discovery.completed", message="old", created_at=old)
        response = self.client.get("/api/health/")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["status"], "degraded")
        self.assertEqual(response.data["workers"]["discovery_cron"]["status"], "stale")
