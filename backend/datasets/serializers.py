"""
Request validation and response shapes for the API.

Input serializers check request bodies and query parameters; output serializers define
the JSON the views return. Business rules live in `datasets.services`, not here.
"""

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
    """Either `instruction` (natural language, sent to the LLM) or `pattern` is required.

    `replacement` and `columns` are optional: when omitted with an instruction, they are
    inferred from it. `flags` only applies to hand-written patterns.
    """

    instruction = serializers.CharField(
        max_length=settings.MAX_INSTRUCTION_LENGTH, required=False, allow_blank=True
    )
    # Whitespace is meaningful in patterns and replacements, so never trim it.
    pattern = serializers.CharField(
        max_length=settings.MAX_PATTERN_LENGTH,
        required=False,
        allow_blank=True,
        trim_whitespace=False,
    )
    replacement = serializers.CharField(
        max_length=settings.MAX_REPLACEMENT_LENGTH,
        required=False,
        allow_blank=True,
        allow_null=True,
        trim_whitespace=False,
    )
    columns = serializers.ListField(
        child=serializers.CharField(), required=False, allow_empty=False
    )
    flags = serializers.ListField(
        child=serializers.ChoiceField(choices=sorted(FLAGS)), required=False, default=list
    )

    def validate(self, attrs):
        if not attrs.get("instruction") and not attrs.get("pattern"):
            raise serializers.ValidationError("Provide either an instruction or a pattern.")
        return attrs


class ExtractRequestSerializer(serializers.Serializer):
    instruction = serializers.CharField(max_length=settings.MAX_INSTRUCTION_LENGTH)
    # Omitted: the LLM picks the column from the instruction.
    column = serializers.CharField(required=False, allow_null=True)


class ExtractSampleSerializer(serializers.Serializer):
    row = serializers.IntegerField()
    value = serializers.CharField()
    # New column name -> extracted text (null when that group captured nothing).
    parts = serializers.DictField(child=serializers.CharField(allow_null=True))


class ClassifyRequestSerializer(serializers.Serializer):
    column = serializers.CharField()
    instruction = serializers.CharField(max_length=settings.MAX_INSTRUCTION_LENGTH)


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
    params = serializers.SerializerMethodField()

    class Meta:
        model = Transformation
        fields = [
            "id",
            "dataset",
            "kind",
            "status",
            "instruction",
            "explanation",
            "pattern",
            "flags",
            "replacement",
            "columns",
            "params",
            "stats",
            "source_version",
            "result_version",
            "created_at",
            "applied_at",
        ]

    def get_params(self, transformation: Transformation) -> dict:
        # The value -> category mapping can hold up to MAX_CLASSIFY_VALUES long strings
        # and is only needed server-side, so it is left out of responses.
        return {key: value for key, value in transformation.params.items() if key != "mapping"}
