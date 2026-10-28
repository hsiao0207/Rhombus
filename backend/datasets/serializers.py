from django.conf import settings
from rest_framework import serializers

from datasets.models import Dataset, DatasetVersion, Transformation
from datasets.services.regex_engine import FLAGS


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


class PreviewRequestSerializer(serializers.Serializer):
    # Whitespace is meaningful in patterns and replacements, so never trim it.
    pattern = serializers.CharField(max_length=settings.MAX_PATTERN_LENGTH, trim_whitespace=False)
    replacement = serializers.CharField(
        max_length=settings.MAX_REPLACEMENT_LENGTH,
        allow_blank=True,
        trim_whitespace=False,
        default="",
    )
    columns = serializers.ListField(
        child=serializers.CharField(), required=False, allow_empty=False
    )
    flags = serializers.ListField(
        child=serializers.ChoiceField(choices=sorted(FLAGS)), required=False, default=list
    )


class CellChangeSerializer(serializers.Serializer):
    row = serializers.IntegerField()
    column = serializers.CharField()
    before = serializers.CharField()
    after = serializers.CharField()


class TransformationSerializer(serializers.ModelSerializer):
    source_version = serializers.IntegerField(source="source_version.version_no")
    result_version = serializers.IntegerField(
        source="result_version.version_no", allow_null=True, default=None
    )

    class Meta:
        model = Transformation
        fields = [
            "id",
            "dataset",
            "status",
            "instruction",
            "pattern",
            "flags",
            "replacement",
            "columns",
            "stats",
            "source_version",
            "result_version",
            "created_at",
            "applied_at",
        ]
