from django.contrib import admin

from datasets.models import Dataset, DatasetVersion


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
