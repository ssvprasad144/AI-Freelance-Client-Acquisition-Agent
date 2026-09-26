from dataclasses import dataclass


@dataclass(frozen=True)
class OutreachDestination:
    medium: str
    action_type: str
    url: str


class SourceAdapter:
    key = "generic"
    def can_handle(self, source: str) -> bool:
        return self.key in (source or "").lower().replace(" ", "_")

    def destination(self, lead) -> OutreachDestination:
        return OutreachDestination("contact_form", "open_contact_form", lead.action_url or lead.source_url)


class MarketplaceAdapter(SourceAdapter):
    key = "marketplace"
    def can_handle(self, source: str) -> bool:
        source = (source or "").lower().replace(" ", "_")
        return any(k in source for k in ("freelancer", "upwork", "fiverr", "peopleperhour", "marketplace"))

    def destination(self, lead):
        return OutreachDestination("marketplace_bid", "open_bid", lead.action_url or lead.source_url)


class LinkedInAdapter(SourceAdapter):
    key = "linkedin"
    def can_handle(self, source: str) -> bool:
        return "linkedin" in (source or "").lower()

    def destination(self, lead):
        return OutreachDestination("linkedin_dm", "open_profile", lead.action_url or lead.source_url)


class RedditAdapter(SourceAdapter):
    key = "reddit"
    def can_handle(self, source: str) -> bool:
        return "reddit" in (source or "").lower()

    def destination(self, lead):
        return OutreachDestination("reddit_reply", "open_post", lead.action_url or lead.source_url)


class GitHubAdapter(SourceAdapter):
    key = "github"
    def can_handle(self, source: str) -> bool:
        return "github" in (source or "").lower()

    def destination(self, lead):
        return OutreachDestination("github_response", "open_issue", lead.action_url or lead.source_url)


class EmailAdapter(SourceAdapter):
    key = "email"
    def can_handle(self, source: str) -> bool:
        return bool((source or "").lower().find("email") >= 0)

    def destination(self, lead):
        return OutreachDestination("email", "send_email", lead.action_url or lead.source_url)


class JobApplicationAdapter(SourceAdapter):
    key = "job"
    def can_handle(self, source: str) -> bool:
        source = (source or "").lower()
        return any(k in source for k in ("job", "startup", "career", "wellfound", "indeed"))

    def destination(self, lead):
        return OutreachDestination("job_application", "open_application", lead.action_url or lead.source_url)


ADAPTERS = (
    MarketplaceAdapter(),
    LinkedInAdapter(),
    RedditAdapter(),
    GitHubAdapter(),
    JobApplicationAdapter(),
)


def resolve_outreach_destination(lead):
    source = (lead.source or "").lower().replace(" ", "_")
    for adapter in ADAPTERS:
        if adapter.can_handle(source):
            return adapter.destination(lead)

    if (lead.contact_info or {}).get("email"):
        return OutreachDestination("email", "send_email", lead.action_url or lead.source_url)

    return SourceAdapter().destination(lead)
