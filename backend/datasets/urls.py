from rest_framework.routers import DefaultRouter

from datasets.views import DatasetViewSet

router = DefaultRouter(trailing_slash=True)
router.register("datasets", DatasetViewSet, basename="dataset")

urlpatterns = router.urls
