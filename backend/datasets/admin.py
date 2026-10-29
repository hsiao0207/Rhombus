"""Django admin pages for inspecting datasets, their versions and transformations."""

from django.contrib import admin

from datasets.models import Dataset, DatasetVersion, Transformation


class DatasetVersionInline(admin.TabularInline):
    model = DatasetVersion
    fk_name = "dataset"
    extra = 0
    readonly_fields = ["version_no", "row_count", "data_file", "created_at"]


@admin.register(Dataset)
class DatasetAdmin(admin.ModelAdmin):
    list_display = ["original_name", "file_format", "file_size", "created_at"]
    readonly_fields = ["id", "created_at"]
    inlines = [DatasetVersionInline]


@admin.register(Transformation)
class TransformationAdmin(admin.ModelAdmin):
    list_display = ["dataset", "pattern", "replacement", "status", "created_at"]
    list_filter = ["status"]
    readonly_fields = ["id", "created_at", "applied_at"]
