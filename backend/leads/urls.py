from django.urls import include,path
from rest_framework.routers import DefaultRouter
from .views import LeadViewSet,activity,dashboard,health
router=DefaultRouter()
router.register("leads",LeadViewSet,basename="lead")
urlpatterns=[path("health/",health),path("dashboard/",dashboard),path("activity/",activity),path("",include(router.urls))]
