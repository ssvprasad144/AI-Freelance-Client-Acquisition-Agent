import time
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone
from leads.discovery_cycle import run_discovery_cycle
from leads.models import ActivityLog

PROFILES=[
    ("ai-automation","current public freelance opportunities for AI products, AI agents, workflow automation, Python automation and business automation"),
    ("django-fullstack","current public freelance opportunities for Django, Django REST Framework, Python backend, React and full-stack development"),
    ("interactive-web","current public freelance opportunities for React, Three.js, WebGL, interactive websites and 3D web development"),
    ("startup-build","current public freelance opportunities from startups seeking an MVP, SaaS prototype, AI MVP or full-stack product developer"),
]

class Command(BaseCommand):
    help="Run the multi-profile client acquisition discovery cycle."
    def add_arguments(self,parser):
        parser.add_argument("--loop",action="store_true")
        parser.add_argument("--interval",type=int,default=settings.DISCOVERY_WORKER_INTERVAL)
        parser.add_argument("--limit",type=int,default=settings.DISCOVERY_MAX_RESULTS)
    def handle(self,*args,**options):
        interval=max(options["interval"],60)
        while True:
            cycle=[]
            for profile,query in PROFILES:
                ActivityLog.objects.create(event_type="worker.discovery.heartbeat",message=f"Acquisition profile started: {profile}.",metadata={"profile":profile})
                try:
                    result=run_discovery_cycle(query=query,source="live",qualification_limit=options["limit"])
                    result["profile"]=profile
                    cycle.append(result)
                    self.stdout.write(self.style.SUCCESS(f"{profile}: created={result['created']} qualified={result['qualified']}"))
                except Exception as exc:
                    ActivityLog.objects.create(event_type="worker.discovery.error",message=f"Acquisition profile failed: {profile}.",metadata={"profile":profile,"error":str(exc)})
                    self.stderr.write(self.style.ERROR(f"{profile}: {exc}"))
                    if not options["loop"]: raise
            ActivityLog.objects.create(event_type="worker.discovery.heartbeat",message="Multi-profile acquisition cycle completed.",metadata={"profiles":len(cycle),"results":cycle})
            if not options["loop"]: break
            try: time.sleep(interval)
            except KeyboardInterrupt:
                self.stdout.write(self.style.WARNING("Acquisition worker stopped."))
                break
