import uuid

from django.core.management.base import BaseCommand
from django.utils import timezone

from leads.autonomous_cycle import run_autonomous_cycle


class Command(BaseCommand):
    help = "Run one autonomous client-acquisition supervisor cycle."

    def handle(self, *args, **options):
        started = timezone.now()
        try:
            result = run_autonomous_cycle()
            self.stdout.write(
                self.style.SUCCESS(
                    "Autonomous cycle: run_id={run_id}, actions={actions}, "
                    "pending_approval={pending}, due_followups={due}, "
                    "duration_ms={duration}".format(
                        run_id=result["run_id"],
                        actions=len(result["actions_executed"]),
                        pending=result["pending_approval"],
                        due=result["due_followups"],
                        duration=result["duration_ms"],
                    )
                )
            )
        except Exception as exc:
            duration_ms = int((timezone.now() - started).total_seconds() * 1000)
            self.stderr.write(
                self.style.ERROR(
                    f"Autonomous cycle failed after {duration_ms}ms: {exc}"
                )
            )
            raise
