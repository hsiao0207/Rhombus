from django.urls import path
from rest_framework.routers import DefaultRouter

from datasets.views import DatasetViewSet, TransformationViewSet, health

router = DefaultRouter(trailing_slash=True)
router.register("datasets", DatasetViewSet, basename="dataset")
router.register("transformations", TransformationViewSet, basename="transformation")

urlpatterns = [path("health/", health, name="health"), *router.urls]
