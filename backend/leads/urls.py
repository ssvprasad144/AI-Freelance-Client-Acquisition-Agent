from django.urls import include,path
from rest_framework.routers import DefaultRouter
from .views import LeadViewSet,activity,dashboard,health,run_discovery,qualify_new_leads,qualified_leads,followups,create_followup,approve_followup,due_followups,process_due_followups
router=DefaultRouter(); router.register("leads",LeadViewSet,basename="lead")
urlpatterns=[path("health/",health),path("dashboard/",dashboard),path("activity/",activity),path("discovery/run/",run_discovery),path("discovery/qualify/",qualify_new_leads),path("leads/qualified/",qualified_leads),path("followups/",followups),path("followups/process-due/",process_due_followups),path("followups/due/",due_followups),path("followups/create/",create_followup),path("followups/<int:pk>/approve/",approve_followup),path("leads/<int:pk>/followups/",create_followup),path("",include(router.urls))]
