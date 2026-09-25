from typing import Any

from .live_provider import LiveDiscoveryError, discover_live
from .mock_provider import DiscoveryError, MockDiscoveryProvider


class DiscoveryService:
    """Source-independent discovery orchestration."""

    def __init__(self):
        self.providers = {
            "mock": MockDiscoveryProvider(),
        }

    def discover(self, query: str, source: str = "live") -> dict[str, Any]:
        query = (query or "").strip()
        if source == "live":
            result = discover_live(query)
            return {"source": "web_search", **result}
        if source not in self.providers:
            raise DiscoveryError(f"Unknown discovery source: {source}")
        leads = self.providers[source].discover(query=query)
        return {"source": source, "leads": leads, "model": "local"}
