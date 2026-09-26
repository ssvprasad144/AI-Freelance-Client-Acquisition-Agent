import time

from django.core.management.base import BaseCommand

from leads.followup_service import process_due_followups


class Command(BaseCommand):
    help = "Process approved follow-ups that have reached their scheduled time."

    def add_arguments(self, parser):
        parser.add_argument(
            "--loop",
            action="store_true",
            help="Keep running and process due follow-ups repeatedly.",
        )
        parser.add_argument(
            "--interval",
            type=int,
            default=60,
            help="Seconds between processing cycles when --loop is enabled.",
        )

    def handle(self, *args, **options):
        interval = max(options["interval"], 10)

        while True:
            result = process_due_followups()
            self.stdout.write(
                self.style.SUCCESS(
                    "Follow-up worker: processed={processed}, due={due}, sent={sent}".format(
                        **result
                    )
                )
            )

            if not options["loop"]:
                break

            try:
                time.sleep(interval)
            except KeyboardInterrupt:
                self.stdout.write(self.style.WARNING("Follow-up worker stopped."))
                break
