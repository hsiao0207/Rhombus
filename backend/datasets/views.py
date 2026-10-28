"""
HTTP layer: validate input, call a service, serialize the result.
Business logic lives in `datasets.services`.
"""

from django.db import connection
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.request import Request
from rest_framework.response import Response

from datasets.models import Dataset, Transformation
from datasets.serializers import (
    CellChangeSerializer,
    DatasetSerializer,
    DatasetUploadSerializer,
    PreviewRequestSerializer,
    RowsQuerySerializer,
    TransformationSerializer,
)
from datasets.services import dataset_service, transformation_service
from datasets.throttles import PreviewThrottle, UploadThrottle


@api_view(["GET"])
def health(request: Request) -> Response:
    """Liveness check for the container orchestrator; also verifies the database."""
    connection.ensure_connection()
    return Response({"status": "ok"})


class DatasetViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = Dataset.objects.select_related("current_version__parent")
    serializer_class = DatasetSerializer

    def get_throttles(self):
        if self.action == "create":
            return [UploadThrottle()]
        return super().get_throttles()

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

    @action(
        detail=True,
        methods=["post"],
        url_path="transformations/preview",
        throttle_classes=[PreviewThrottle],
    )
    def preview_transformation(self, request: Request, pk=None) -> Response:
        params = PreviewRequestSerializer(data=request.data)
        params.is_valid(raise_exception=True)
        data = params.validated_data
        dataset = self.get_object()
        if data.get("pattern"):
            result = transformation_service.preview(
                dataset,
                pattern=data["pattern"],
                replacement=data.get("replacement") or "",
                flags=data["flags"],
                columns=data.get("columns"),
                instruction=data.get("instruction", ""),
            )
        else:
            result = transformation_service.preview_from_instruction(
                dataset,
                instruction=data["instruction"],
                replacement=data.get("replacement"),
                columns=data.get("columns"),
            )
        return Response(
            {
                "transformation": TransformationSerializer(result.transformation).data,
                "samples": CellChangeSerializer(result.samples, many=True).data,
            },
            status=status.HTTP_201_CREATED,
        )


class TransformationViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = Transformation.objects.select_related("source_version", "result_version")
    serializer_class = TransformationSerializer

    @action(detail=True, methods=["post"])
    def apply(self, request: Request, pk=None) -> Response:
        transformation = transformation_service.apply(self.get_object())
        dataset = Dataset.objects.select_related("current_version").get(
            pk=transformation.dataset_id
        )
        return Response(
            {
                "transformation": TransformationSerializer(transformation).data,
                "dataset": DatasetSerializer(dataset).data,
            }
        )
