"""
Use cases for datasets: creating one from an upload and reading its rows.

Views stay thin and delegate here; this module orchestrates validation, parsing,
storage and persistence, while `file_io` handles the raw file formats.
"""

import logging
import math

from django.conf import settings
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction

from datasets.exceptions import FileTooLarge
from datasets.models import Dataset, DatasetVersion
from datasets.services import file_io

logger = logging.getLogger(__name__)


def create_dataset(upload: UploadedFile) -> Dataset:
    """Validate and parse an upload, then store it as a dataset with version 1."""
    if upload.size > settings.MAX_UPLOAD_SIZE_BYTES:
        raise FileTooLarge(
            f"Files must be {settings.MAX_UPLOAD_SIZE_MB} MB or smaller.",
            details={"max_size_mb": settings.MAX_UPLOAD_SIZE_MB, "size_bytes": upload.size},
        )

    file_format = file_io.detect_format(upload.name)
    df = file_io.read_tabular(upload, file_format)

    with transaction.atomic():
        upload.seek(0)
        dataset = Dataset(
            original_name=upload.name,
            file_format=file_format,
            file_size=upload.size,
        )
        dataset.original_file.save(upload.name, upload, save=False)
        dataset.save()

        version = DatasetVersion(
            dataset=dataset,
            version_no=1,
            row_count=len(df),
            columns=file_io.infer_column_kinds(df),
        )
        version.data_file.name = file_io.save_parquet(
            df, f"datasets/{dataset.id}/versions/v1.parquet"
        )
        version.save()

        dataset.current_version = version
        dataset.save(update_fields=["current_version"])

    logger.info("Created dataset %s (%d rows, %s)", dataset.id, len(df), file_format)
    return dataset


def get_rows(dataset: Dataset, page: int, page_size: int) -> dict:
    """Return one page of the dataset's current version."""
    version = dataset.current_version
    result = file_io.read_page(version.data_file.name, (page - 1) * page_size, page_size)
    return {
        "version": version.version_no,
        "page": page,
        "page_size": page_size,
        "total_rows": result.total_rows,
        "total_pages": math.ceil(result.total_rows / page_size),
        "columns": result.columns,
        "rows": result.rows,
    }
