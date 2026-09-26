import time
from django.conf import settings
from django.core.management.base import BaseCommand
from leads.followup_service import process_due_followups
from leads.models import ActivityLog

class Command(BaseCommand):
    help="Process approved follow-ups that have reached their scheduled time; use --loop only for local/worker execution."
    def add_arguments(self,parser):
        parser.add_argument("--loop",action="store_true"); parser.add_argument("--interval",type=int,default=settings.FOLLOWUP_WORKER_INTERVAL)
    def handle(self,*args,**options):
        interval=max(options["interval"],10)
        while True:
            ActivityLog.objects.create(event_type="worker.followup.heartbeat",message="Follow-up worker cycle started.",metadata={"interval":interval})
            try:
                result=process_due_followups()
                self.stdout.write(self.style.SUCCESS("Follow-up worker: processed={processed}, due={due}, sent={sent}".format(**result)))
                ActivityLog.objects.create(event_type="worker.followup.heartbeat",message="Follow-up worker cycle completed.",metadata=result)
            except Exception as exc:
                ActivityLog.objects.create(event_type="worker.followup.error",message="Follow-up worker cycle failed.",metadata={"error":str(exc)})
                raise
            if not options["loop"]: break
            try: time.sleep(interval)
            except KeyboardInterrupt: self.stdout.write(self.style.WARNING("Follow-up worker stopped.")); break
