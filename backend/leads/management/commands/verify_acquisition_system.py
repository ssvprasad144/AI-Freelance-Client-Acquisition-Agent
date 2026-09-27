from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from leads.lifecycle_service import validate_workspace


class Command(BaseCommand):
    help = "Verify single-owner acquisition lifecycle invariants."

    def add_arguments(self, parser):
        parser.add_argument("--owner-id", type=int, default=None)
        parser.add_argument("--allow-ownerless", action="store_true")

    def handle(self, *args, **options):
        User=get_user_model()
        owner=User.objects.filter(pk=options["owner_id"]).first() if options["owner_id"] else User.objects.order_by("id").first()
        if not owner:
            raise CommandError("No owner user exists.")
        report=validate_workspace(owner)
        if options["allow_ownerless"]:
            report["ok"]=not report["violations"]
        self.stdout.write(self.style.SUCCESS(str(report)) if report["ok"] else self.style.ERROR(str(report)))
        if not report["ok"]:
            raise CommandError("Acquisition lifecycle verification failed.")
