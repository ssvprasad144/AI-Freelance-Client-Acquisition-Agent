"""Conservative validation helpers for externally discovered lead data."""

import ipaddress
import re
from datetime import datetime, timedelta, timezone as dt_timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.utils import timezone


TRACKING_PARAMETERS = {"fbclid", "gclid", "mc_cid", "mc_eid"}
TRACKING_PREFIXES = ("utm_",)
PLACEHOLDER_EMAIL_DOMAINS = {"example.com", "example.org", "example.net", "invalid", "localhost"}


def normalize_url(value):
    """Validate and canonicalize an HTTP(S) URL without changing its destination."""
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("URL must be a non-empty string without surrounding whitespace.")
    if any(ord(char) < 32 or ord(char) == 127 or char.isspace() for char in value):
        raise ValueError("URL contains control characters.")
    if len(value) > 4096:
        raise ValueError("URL exceeds the supported input length.")
    try:
        parts = urlsplit(value)
        port = parts.port  # Access validates malformed/out-of-range ports.
    except ValueError as exc:
        raise ValueError("URL structure is malformed.") from exc
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        raise ValueError("Only absolute HTTP(S) URLs are accepted.")
    if parts.username is not None or parts.password is not None:
        raise ValueError("URLs containing embedded credentials are not accepted.")
    host = parts.hostname.rstrip(".").lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".localhost"):
        raise ValueError("Localhost URLs are not accepted.")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address and not address.is_global:
        raise ValueError("Non-public IP URLs are not accepted.")
    if not address:
        try:
            host = host.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise ValueError("URL hostname is malformed.") from exc
        if not re.fullmatch(r"[a-z0-9.-]+", host) or ".." in host:
            raise ValueError("URL hostname is malformed.")
    if parts.path and not parts.path.startswith("/"):
        raise ValueError("URL path is malformed.")

    netloc = host
    if address and address.version == 6:
        netloc = f"[{address.compressed}]"
    else:
        netloc = host
    if port and not ((parts.scheme.lower() == "http" and port == 80) or (parts.scheme.lower() == "https" and port == 443)):
        netloc = f"{netloc}:{port}"
    query = urlencode(
        [(key, val) for key, val in parse_qsl(parts.query, keep_blank_values=True)
         if key.lower() not in TRACKING_PARAMETERS and not key.lower().startswith(TRACKING_PREFIXES)],
        doseq=True,
    )
    path = parts.path or "/"
    if path != "/":
        path = path.rstrip("/")
    normalized = urlunsplit((parts.scheme.lower(), netloc, path, query, ""))
    if len(normalized) > 2048:
        raise ValueError("URL exceeds the supported storage length.")
    return normalized


def validate_discovered_email(value):
    """Return a normalized syntactically valid email, or None for absent data."""
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise ValueError("Email must be a string.")
    email = value.strip().casefold()
    if len(email) > 254:
        raise ValueError("Email exceeds the supported length.")
    try:
        validate_email(email)
    except ValidationError as exc:
        raise ValueError("Email address has invalid syntax.") from exc
    domain = email.rsplit("@", 1)[-1]
    if domain in PLACEHOLDER_EMAIL_DOMAINS or domain.endswith(".test") or domain.endswith(".invalid"):
        raise ValueError("Placeholder email addresses are not accepted.")
    return email


def source_supported_evidence(evidence, findings):
    """Keep only evidence snippets that literally occur in retrieved findings."""
    if not isinstance(evidence, list) or not isinstance(findings, str):
        return []
    accepted = []
    cited_urls = set()
    for candidate in re.findall(r"https?://[^\s\])}>]+", findings, flags=re.IGNORECASE):
        candidate = candidate.rstrip(".,;:")
        try:
            cited_urls.add(normalize_url(candidate))
        except ValueError:
            continue
    for row in evidence:
        if not isinstance(row, dict):
            continue
        field = row.get("field")
        value = row.get("value")
        source_url = row.get("source_url")
        excerpt = row.get("excerpt")
        if not all(isinstance(item, str) and item.strip() for item in (field, value, source_url, excerpt)):
            continue
        try:
            normalized_source = normalize_url(source_url)
        except ValueError:
            continue
        if (normalized_source not in cited_urls or excerpt.strip() not in findings
                or value.strip().casefold() not in excerpt.strip().casefold()):
            continue
        accepted.append({
            "field": field.strip()[:80],
            "value": value.strip()[:2000],
            "source_url": normalized_source,
            "excerpt": excerpt.strip()[:2000],
        })
    return accepted


def validate_lead_record(item, findings=""):
    """Validate/canonicalize a provider row and retain only grounded evidence."""
    if not isinstance(item, dict):
        raise ValueError("Lead result must be an object.")
    cleaned = dict(item)
    for name, maximum in (("title", 255), ("description", 20000)):
        value = cleaned.get(name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} is required.")
        cleaned[name] = value.strip()
        if len(cleaned[name]) > maximum:
            raise ValueError(f"{name} exceeds {maximum} characters.")
    for name, maximum in (("company", 255), ("budget_text", 255), ("location", 255),
                          ("company_description", 20000), ("hiring_signal", 4000)):
        value = cleaned.get(name, "")
        if not isinstance(value, str):
            raise ValueError(f"{name} must be a string.")
        cleaned[name] = value.strip()[:maximum]
    source = cleaned.get("source") or "web_search"
    if not isinstance(source, str) or len(source.strip()) > 100:
        raise ValueError("source must be a string no longer than 100 characters.")
    cleaned["source"] = source.strip() or "web_search"
    cleaned["source_url"] = normalize_url(cleaned.get("source_url"))
    cleaned["action_url"] = normalize_url(cleaned.get("action_url") or cleaned["source_url"])
    company_website = cleaned.get("company_website") or ""
    if company_website:
        cleaned["company_website"] = normalize_url(company_website)
    else:
        cleaned["company_website"] = ""
    if cleaned.get("lead_type", "freelance") not in {"freelance", "direct", "startup", "other"}:
        raise ValueError("lead_type is invalid.")
    technologies = cleaned.get("technologies", [])
    if not isinstance(technologies, list) or any(not isinstance(value, str) for value in technologies):
        raise ValueError("technologies must be a list of strings.")
    cleaned["technologies"] = list(dict.fromkeys(value.strip()[:100] for value in technologies if value.strip()))[:30]
    contact = cleaned.get("contact_info") or {}
    if not isinstance(contact, dict):
        raise ValueError("contact_info must be an object.")
    contact = {key: value for key, value in contact.items() if key in {"name", "email", "phone", "profile_url", "role"}}
    for key, value in contact.items():
        if not isinstance(value, str):
            raise ValueError(f"contact_info.{key} must be a string.")
        contact[key] = value.strip()
    if contact.get("email"):
        contact["email"] = validate_discovered_email(contact["email"])
    if contact.get("profile_url"):
        contact["profile_url"] = normalize_url(contact["profile_url"])
    cleaned["contact_info"] = contact
    for key in ("posted_at", "expires_at"):
        value = cleaned.get(key) or None
        if value is not None:
            if not isinstance(value, str):
                raise ValueError(f"{key} must be an ISO-8601 timestamp or empty.")
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError(f"{key} is not a valid ISO-8601 timestamp.") from exc
            if timezone.is_naive(parsed):
                parsed = timezone.make_aware(parsed, timezone=dt_timezone.utc)
            cleaned[key] = parsed
        else:
            cleaned[key] = None
    if cleaned["posted_at"] and cleaned["expires_at"]:
        if cleaned["expires_at"] <= cleaned["posted_at"]:
            raise ValueError("expires_at must be later than posted_at.")
    if cleaned["expires_at"] and cleaned["expires_at"] <= timezone.now():
        raise ValueError("Opportunity is already expired.")
    if cleaned["posted_at"] and cleaned["posted_at"] > timezone.now() + timedelta(days=1):
        raise ValueError("posted_at is implausibly far in the future.")
    supported = source_supported_evidence(cleaned.get("evidence", []), findings)
    values = {
        "title": cleaned["title"], "company": cleaned["company"],
        "company_website": cleaned["company_website"], "description": cleaned["description"],
        "company_description": cleaned["company_description"], "location": cleaned["location"],
        "hiring_signal": cleaned["hiring_signal"], "budget_text": cleaned["budget_text"],
        "source_url": cleaned["source_url"], "action_url": cleaned["action_url"],
        "posted_at": cleaned["posted_at"].isoformat() if cleaned["posted_at"] else "",
        "expires_at": cleaned["expires_at"].isoformat() if cleaned["expires_at"] else "",
    }
    values.update({f"contact_info.{key}": value for key, value in contact.items()})
    values.update({f"technologies.{index}": value for index, value in enumerate(cleaned["technologies"])})
    cleaned["evidence"] = [row for row in supported if values.get(row["field"], "").casefold() == row["value"].casefold()]
    return cleaned

