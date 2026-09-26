import time

from django.conf import settings
from django.core.management.base import BaseCommand

from leads.discovery.profiles import select_profile
from leads.discovery_cycle import run_discovery_cycle
from leads.models import ActivityLog


class Command(BaseCommand):
    help = "Run one rotating client-acquisition discovery profile per cycle."

    def add_arguments(self, parser):
        parser.add_argument("--loop", action="store_true")
        parser.add_argument("--interval", type=int, default=settings.DISCOVERY_WORKER_INTERVAL)
        parser.add_argument("--limit", type=int, default=settings.DISCOVERY_MAX_RESULTS)

    def handle(self, *args, **options):
        interval = max(options["interval"], 60)
        while True:
            profile = select_profile(
                settings.DISCOVERY_QUERY_CACHE_TTL_HOURS,
                only_if_due=False,
            )
            ActivityLog.objects.create(
                event_type="worker.discovery.heartbeat",
                message=f"Acquisition profile started: {profile['id']}.",
                metadata={"profile": profile["id"], "interval": interval},
            )
            try:
                result = run_discovery_cycle(
                    query=profile["query"],
                    source="live",
                    qualification_limit=options["limit"],
                    profile_id=profile["id"],
                )
                result["profile"] = profile["id"]
                self.stdout.write(
                    self.style.SUCCESS(
                        f"{profile['id']}: searched={result.get('searched', False)} "
                        f"created={result['created']} qualified={result['qualified']}"
                    )
                )
                ActivityLog.objects.create(
                    event_type="worker.discovery.heartbeat",
                    message="Rotating acquisition profile completed.",
                    metadata=result,
                )
            except Exception as exc:
                ActivityLog.objects.create(
                    event_type="worker.discovery.error",
                    message=f"Acquisition profile failed: {profile['id']}.",
                    metadata={"profile": profile["id"], "error": str(exc)},
                )
                self.stderr.write(self.style.ERROR(f"{profile['id']}: {exc}"))
                if not options["loop"]:
                    raise
            if not options["loop"]:
                break
            try:
                time.sleep(interval)
            except KeyboardInterrupt:
                self.stdout.write(self.style.WARNING("Acquisition worker stopped."))
                break
