from __future__ import annotations

import re
from urllib.parse import urlsplit


def normalize_url(value: str) -> str:
    try:
        parts = urlsplit(str(value).strip())
        host = (parts.hostname or "").lower().removeprefix("www.")
        path = (parts.path or "").rstrip("/")
        return f"{host}{path}"
    except (TypeError, ValueError):
        return str(value).strip().lower().rstrip("/")


def _source_excerpts_by_url(source_findings) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    if not isinstance(source_findings, list):
        return result
    for finding in source_findings:
        if not isinstance(finding, dict):
            continue
        url = str(finding.get("url") or finding.get("source_url") or "").strip()
        excerpt = str(finding.get("excerpt") or "").strip()
        if not url or not excerpt:
            continue
        result.setdefault(normalize_url(url), []).append(excerpt)
    return result


def source_supported_evidence(value, source_url: str, source_findings) -> bool:
    if value in (None, "", [], {}) or not source_url:
        return False
    excerpts = _source_excerpts_by_url(source_findings).get(normalize_url(source_url), [])
    value_text = re.sub(r"\s+", " ", str(value)).strip().lower()
    return bool(value_text and any(value_text in re.sub(r"\s+", " ", excerpt).strip().lower() for excerpt in excerpts))


def validate_lead_record(item: dict, source_findings=None) -> dict:
    source_url = str(item.get("source_url") or "").strip()
    fields = {}
    for field in ("title", "company", "description", "budget_text", "source_url", "action_url"):
        value = item.get(field)
        if value not in (None, "", [], {}):
            fields[field] = source_supported_evidence(value, source_url, source_findings or [])
    return {
        "valid": bool(item.get("title") and item.get("description") and source_url),
        "source_url": source_url,
        "source_supported_fields": fields,
    }
