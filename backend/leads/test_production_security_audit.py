from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from .models import Lead, FollowUp
from .discovery.public_crawler import _public_host, CrawlError


class ProductionSecurityTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(username="audit-owner", password="audit-password-123")
        self.api = APIClient()

    def test_login_rotates_and_logout_revokes(self):
        old = Token.objects.create(user=self.user)
        response = self.api.post("/api/auth/login/", {"username": self.user.username, "password": "audit-password-123"})
        self.assertEqual(response.status_code, 200)
        key = response.data["token"]
        self.assertNotEqual(old.key, key)
        self.api.credentials(HTTP_AUTHORIZATION="Token " + old.key)
        self.assertEqual(self.api.get("/api/auth/me/").status_code, 401)
        self.api.credentials(HTTP_AUTHORIZATION="Token " + key)
        self.assertEqual(self.api.post("/api/auth/logout/").status_code, 204)
        self.assertEqual(self.api.get("/api/auth/me/").status_code, 401)

    @override_settings(AUTH_TOKEN_TTL_HOURS=1)
    def test_expired_token(self):
        token = Token.objects.create(user=self.user)
        Token.objects.filter(pk=token.pk).update(created=timezone.now()-timedelta(hours=2))
        self.api.credentials(HTTP_AUTHORIZATION="Token " + token.key)
        self.assertEqual(self.api.get("/api/auth/me/").status_code, 401)

    def test_login_throttle(self):
        for _ in range(5):
            self.assertEqual(self.api.post("/api/auth/login/", {"username":"unknown","password":"bad"}).status_code, 400)
        self.assertEqual(self.api.post("/api/auth/login/", {"username":"unknown","password":"bad"}).status_code, 429)

    def test_followup_processing_is_owner_scoped(self):
        other = get_user_model().objects.create_user(username="other-audit")
        lead = Lead.objects.create(owner=other, title="Other lead", source="direct", source_url="https://example.com/other")
        followup = FollowUp.objects.create(lead=lead, message="Private", scheduled_at=timezone.now()-timedelta(hours=1), status="approved")
        self.api.force_authenticate(self.user)
        self.assertEqual(self.api.post("/api/followups/process-due/").status_code, 200)
        followup.refresh_from_db()
        self.assertEqual(followup.status, "approved")

    @patch("leads.discovery.public_crawler.socket.getaddrinfo")
    def test_non_global_address_rejected(self, resolve):
        resolve.return_value = [(2, 1, 6, "", ("100.64.0.1", 0))]
        with self.assertRaises(CrawlError):
            _public_host("example.com")
