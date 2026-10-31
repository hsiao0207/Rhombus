"""
Data model.

A `Dataset` is one uploaded file. Its contents live in immutable `DatasetVersion`s:
version 1 is the parsed upload, and every applied transformation produces a new version.
Never mutating data in place makes undo and before/after comparison straightforward.
"""

import uuid

from django.db import models


def original_upload_path(instance: "Dataset", filename: str) -> str:
    return f"datasets/{instance.id}/original/{filename}"


def version_data_path(instance: "DatasetVersion", filename: str) -> str:
    return f"datasets/{instance.dataset_id}/versions/{filename}"


class Dataset(models.Model):
    class FileFormat(models.TextChoices):
        CSV = "csv", "CSV"
        XLSX = "xlsx", "Excel"

    # UUIDs keep dataset URLs unguessable on a public deployment.
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    original_name = models.CharField(max_length=255)
    file_format = models.CharField(max_length=8, choices=FileFormat.choices)
    original_file = models.FileField(upload_to=original_upload_path)
    file_size = models.PositiveBigIntegerField()
    current_version = models.ForeignKey(
        "DatasetVersion",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.original_name


class DatasetVersion(models.Model):
    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE, related_name="versions")
    version_no = models.PositiveIntegerField()
    parent = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="children"
    )
    data_file = models.FileField(upload_to=version_data_path)
    row_count = models.PositiveIntegerField()
    # Stored per version because transformations may add columns.
    # Shape: [{"name": "Email", "kind": "text"}, ...]
    columns = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["dataset", "version_no"]
        constraints = [
            models.UniqueConstraint(
                fields=["dataset", "version_no"], name="unique_version_per_dataset"
            )
        ]

    def __str__(self) -> str:
        return f"{self.dataset} v{self.version_no}"


class Transformation(models.Model):
    """
    One operation on a dataset: a regex find-and-replace, or an LLM classification that
    adds a category column. It is created when the user previews it and becomes `applied`
    once the result has been stored as a new dataset version.
    """

    class Kind(models.TextChoices):
        REPLACE = "replace", "Find and replace"
        CLASSIFY = "classify", "Classify"

    class Status(models.TextChoices):
        PREVIEWED = "previewed", "Previewed"
        APPLIED = "applied", "Applied"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE, related_name="transformations")
    source_version = models.ForeignKey(DatasetVersion, on_delete=models.CASCADE, related_name="+")
    result_version = models.ForeignKey(
        DatasetVersion, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.REPLACE)
    # The user's natural-language request (empty when the pattern was entered by hand).
    instruction = models.TextField(blank=True)
    # The LLM's plain-language description of the pattern (empty for hand-written ones).
    explanation = models.TextField(blank=True)
    # Find-and-replace only.
    pattern = models.TextField(blank=True)
    flags = models.JSONField(default=list)
    replacement = models.TextField(blank=True)
    # Columns read by the operation.
    columns = models.JSONField()
    # Classify only: source/new column, categories and the value -> category mapping
    # decided at preview time (see classification_service).
    params = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PREVIEWED)
    # Replace: regex_engine.ReplaceResult.stats plus "total_rows" (see transformation_service).
    # Classify: see classification_service.
    stats = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    applied_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        if self.kind == self.Kind.CLASSIFY:
            return f"classify {self.params.get('source_column')!r} ({self.status})"
        return f"{self.pattern!r} -> {self.replacement!r} ({self.status})"
