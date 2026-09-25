import json
from pathlib import Path
from typing import Any

from django.conf import settings


REQUIRED_FIELDS = ("title", "description")


class DiscoveryError(Exception):
    """Raised when a discovery provider cannot complete its work."""


class MockDiscoveryProvider:
    name = "mock"

    def discover(self, query: str = "") -> list[dict[str, Any]]:
        path = settings.MOCK_LEADS_FILE
        if not path.exists():
            raise DiscoveryError(f"Mock dataset not found: {path}")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DiscoveryError(f"Could not read mock dataset: {exc}") from exc
        if not isinstance(data, list):
            raise DiscoveryError("Mock dataset must contain a JSON array.")

        normalized = []
        query_terms = [x.strip().lower() for x in query.split() if x.strip()]
        for raw in data:
            if not isinstance(raw, dict) or any(not raw.get(field) for field in REQUIRED_FIELDS):
                continue
            item = dict(raw)
            item["technologies"] = item.get("technologies") or []
            if isinstance(item["technologies"], str):
                item["technologies"] = [x.strip() for x in item["technologies"].split(",") if x.strip()]
            item["contact_info"] = item.get("contact_info") or {}
            haystack = " ".join([
                str(item.get("title", "")),
                str(item.get("company", "")),
                str(item.get("description", "")),
                str(item.get("budget_text", "")),
                " ".join(map(str, item["technologies"])),
            ]).lower()
            if query_terms and not all(term in haystack for term in query_terms):
                continue
            normalized.append(item)
        return normalized
