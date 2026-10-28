from rest_framework.routers import DefaultRouter

from datasets.views import DatasetViewSet, TransformationViewSet

router = DefaultRouter(trailing_slash=True)
router.register("datasets", DatasetViewSet, basename="dataset")
router.register("transformations", TransformationViewSet, basename="transformation")

urlpatterns = router.urls
