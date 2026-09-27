from unittest.mock import patch

from django.test import SimpleTestCase

from .discovery.public_crawler import CrawlError, _validate_url


class CrawlerSecurityTests(SimpleTestCase):
    @patch("leads.discovery.public_crawler.socket.getaddrinfo")
    def test_public_url_validation_returns_resolved_public_addresses(self, getaddrinfo):
        getaddrinfo.return_value = [
            (2, 1, 6, "", ("93.184.216.34", 0)),
            (2, 1, 6, "", ("93.184.216.34", 0)),
        ]

        parsed, addresses = _validate_url("https://example.com/jobs/1")

        self.assertEqual(parsed.hostname, "example.com")
        self.assertEqual(addresses, ("93.184.216.34",))
        getaddrinfo.assert_called_once_with("example.com", None, type=2)

    @patch("leads.discovery.public_crawler.socket.getaddrinfo")
    def test_private_dns_answer_is_blocked_before_connection(self, getaddrinfo):
        getaddrinfo.return_value = [
            (2, 1, 6, "", ("10.0.0.8", 0)),
        ]

        with self.assertRaisesMessage(CrawlError, "Private or non-public destination blocked."):
            _validate_url("https://attacker.example/")

    @patch("leads.discovery.public_crawler.socket.getaddrinfo")
    def test_loopback_dns_answer_is_blocked(self, getaddrinfo):
        getaddrinfo.return_value = [
            (2, 1, 6, "", ("127.0.0.1", 0)),
        ]

        with self.assertRaisesMessage(CrawlError, "Private or non-public destination blocked."):
            _validate_url("https://attacker.example/")
