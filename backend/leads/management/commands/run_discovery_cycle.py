import time
import uuid

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from leads.discovery_cycle import run_discovery_cycle
from leads.models import ActivityLog


class Command(BaseCommand):
    help = "Run one optimized live freelance discovery cycle; use --loop only for local/worker execution."

    def add_arguments(self, parser):
        parser.add_argument("--query", default=None)
        parser.add_argument("--source", choices=["live", "mock"], default="live")
        parser.add_argument("--limit", type=int, default=settings.DISCOVERY_MAX_RESULTS)
        parser.add_argument("--loop", action="store_true")
        parser.add_argument("--interval", type=int, default=settings.DISCOVERY_WORKER_INTERVAL)

    def handle(self, *args, **options):
        interval = max(options["interval"], 60)
        while True:
            run_id = uuid.uuid4().hex
            started_at = timezone.now()
            ActivityLog.objects.create(
                event_type="cron.discovery.started",
                message="Discovery Cron execution started.",
                metadata={"run_id": run_id, "interval": interval, "loop": bool(options["loop"])},
            )
            try:
                result = run_discovery_cycle(options["query"], options["source"], options["limit"])
                duration_ms = int((timezone.now() - started_at).total_seconds() * 1000)
                result["run_id"] = run_id
                result["duration_ms"] = duration_ms
                self.stdout.write(
                    self.style.SUCCESS(
                        "Discovery Cron: run_id={run_id}, profile={profile_id}, cached={cached}, "
                        "discovered={discovered}, created={created}, analyzed={analyzed}, qualified={qualified}, "
                        "duration_ms={duration_ms}".format(**result)
                    )
                )
                ActivityLog.objects.create(
                    event_type="cron.discovery.completed",
                    message="Discovery Cron execution completed.",
                    metadata=result,
                )
            except Exception as exc:
                duration_ms = int((timezone.now() - started_at).total_seconds() * 1000)
                metadata = {"run_id": run_id, "duration_ms": duration_ms, "error": str(exc)}
                ActivityLog.objects.create(
                    event_type="cron.discovery.failed",
                    message="Discovery Cron execution failed.",
                    metadata=metadata,
                )
                self.stderr.write(self.style.ERROR(f"Discovery Cron error: run_id={run_id}, duration_ms={duration_ms}, error={exc}"))
                if not options["loop"]:
                    raise
            if not options["loop"]:
                break
            try:
                time.sleep(interval)
            except KeyboardInterrupt:
                self.stdout.write(self.style.WARNING("Discovery Cron stopped."))
                break
