from django.urls import include,path
from rest_framework.routers import DefaultRouter
from .views import LeadViewSet,activity,dashboard,health,run_discovery,qualify_new_leads
router=DefaultRouter(); router.register("leads",LeadViewSet,basename="lead")
urlpatterns=[path("health/",health),path("dashboard/",dashboard),path("activity/",activity),path("discovery/run/",run_discovery),path("discovery/qualify/",qualify_new_leads),path("",include(router.urls))]
