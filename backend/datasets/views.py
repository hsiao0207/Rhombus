"""
HTTP layer: validate input, call a service, serialize the result.
Business logic lives in `datasets.services`.
"""

from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from datasets.models import Dataset
from datasets.serializers import DatasetSerializer, DatasetUploadSerializer, RowsQuerySerializer
from datasets.services import dataset_service


class DatasetViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = Dataset.objects.select_related("current_version")
    serializer_class = DatasetSerializer

    def create(self, request: Request) -> Response:
        upload = DatasetUploadSerializer(data=request.data)
        upload.is_valid(raise_exception=True)
        dataset = dataset_service.create_dataset(upload.validated_data["file"])
        return Response(DatasetSerializer(dataset).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"])
    def rows(self, request: Request, pk=None) -> Response:
        query = RowsQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        data = dataset_service.get_rows(self.get_object(), **query.validated_data)
        return Response(data)
