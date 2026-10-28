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
