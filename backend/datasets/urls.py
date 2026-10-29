"""
API routes, mounted under `/api/`.

    GET  health/                                  liveness check
    POST datasets/                                upload a CSV or Excel file
    GET  datasets/{id}/                           dataset metadata and current version
    GET  datasets/{id}/rows/                      paginated rows with changed cells
    POST datasets/{id}/transformations/preview/   preview a find-and-replace
    GET  transformations/{id}/                    a previewed or applied transformation
    POST transformations/{id}/apply/              apply a preview as a new version
"""

from django.urls import path
from rest_framework.routers import DefaultRouter

from datasets.views import DatasetViewSet, TransformationViewSet, health

router = DefaultRouter(trailing_slash=True)
router.register("datasets", DatasetViewSet, basename="dataset")
router.register("transformations", TransformationViewSet, basename="transformation")

urlpatterns = [path("health/", health, name="health"), *router.urls]
