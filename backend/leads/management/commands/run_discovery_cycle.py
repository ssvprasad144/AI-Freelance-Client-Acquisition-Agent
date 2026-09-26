import time

from django.conf import settings
from django.core.management.base import BaseCommand

from leads.discovery_cycle import run_discovery_cycle


class Command(BaseCommand):
    help = "Run live freelance discovery and automatically qualify new leads."

    def add_arguments(self, parser):
        parser.add_argument("--query", default=settings.DEFAULT_DISCOVERY_QUERY)
        parser.add_argument("--source", choices=["live", "mock"], default="live")
        parser.add_argument("--limit", type=int, default=settings.DISCOVERY_MAX_RESULTS)
        parser.add_argument("--loop", action="store_true")
        parser.add_argument("--interval", type=int, default=settings.DISCOVERY_WORKER_INTERVAL)

    def handle(self, *args, **options):
        interval = max(options["interval"], 60)
        while True:
            try:
                result = run_discovery_cycle(options["query"], options["source"], options["limit"])
                self.stdout.write(self.style.SUCCESS(
                    "Discovery worker: discovered={discovered}, created={created}, duplicates={duplicates}, "
                    "analyzed={analyzed}, qualified={qualified}".format(**result)
                ))
            except Exception as exc:
                self.stderr.write(self.style.ERROR(f"Discovery worker error: {exc}"))
                if not options["loop"]:
                    raise
            if not options["loop"]:
                break
            try:
                time.sleep(interval)
            except KeyboardInterrupt:
                self.stdout.write(self.style.WARNING("Discovery worker stopped."))
                break
