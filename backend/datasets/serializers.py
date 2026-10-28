from django.conf import settings
from rest_framework import serializers

from datasets.models import Dataset, DatasetVersion


class DatasetUploadSerializer(serializers.Serializer):
    file = serializers.FileField(allow_empty_file=False)


class RowsQuerySerializer(serializers.Serializer):
    page = serializers.IntegerField(min_value=1, default=1)
    page_size = serializers.IntegerField(
        min_value=1, max_value=settings.MAX_PAGE_SIZE, default=settings.DEFAULT_PAGE_SIZE
    )


class DatasetVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = DatasetVersion
        fields = ["version_no", "row_count", "columns", "created_at"]


class DatasetSerializer(serializers.ModelSerializer):
    current_version = DatasetVersionSerializer(read_only=True)

    class Meta:
        model = Dataset
        fields = [
            "id",
            "original_name",
            "file_format",
            "file_size",
            "current_version",
            "created_at",
        ]
