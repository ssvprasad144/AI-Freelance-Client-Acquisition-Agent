import time
import uuid

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from leads.followup_service import process_due_followups
from leads.models import ActivityLog


class Command(BaseCommand):
    help = "Process approved follow-ups that have reached their scheduled time; use --loop only for local/worker execution."

    def add_arguments(self, parser):
        parser.add_argument("--loop", action="store_true")
        parser.add_argument("--interval", type=int, default=settings.FOLLOWUP_WORKER_INTERVAL)

    def handle(self, *args, **options):
        interval = max(options["interval"], 10)
        while True:
            run_id = uuid.uuid4().hex
            started_at = timezone.now()
            ActivityLog.objects.create(
                event_type="cron.followup.started",
                message="Follow-up Cron execution started.",
                metadata={"run_id": run_id, "interval": interval, "loop": bool(options["loop"])},
            )
            try:
                result = process_due_followups()
                duration_ms = int((timezone.now() - started_at).total_seconds() * 1000)
                result["run_id"] = run_id
                result["duration_ms"] = duration_ms
                self.stdout.write(
                    self.style.SUCCESS(
                        "Follow-up Cron: run_id={run_id}, processed={processed}, due={due}, sent={sent}, "
                        "duration_ms={duration_ms}".format(**result)
                    )
                )
                ActivityLog.objects.create(
                    event_type="cron.followup.completed",
                    message="Follow-up Cron execution completed.",
                    metadata=result,
                )
            except Exception as exc:
                duration_ms = int((timezone.now() - started_at).total_seconds() * 1000)
                ActivityLog.objects.create(
                    event_type="cron.followup.failed",
                    message="Follow-up Cron execution failed.",
                    metadata={"run_id": run_id, "duration_ms": duration_ms, "error": str(exc)},
                )
                self.stderr.write(self.style.ERROR(f"Follow-up Cron error: run_id={run_id}, duration_ms={duration_ms}, error={exc}"))
                raise
            if not options["loop"]:
                break
            try:
                time.sleep(interval)
            except KeyboardInterrupt:
                self.stdout.write(self.style.WARNING("Follow-up Cron stopped."))
                break
