"""
Use cases for datasets: creating one from an upload, adding versions and reading rows.

Views stay thin and delegate here; this module orchestrates validation, parsing,
storage and persistence, while `file_io` handles the raw file formats.
"""

import logging
import math

import pandas as pd
from django.conf import settings
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from django.db.models import Max

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
        add_version(dataset, df, parent=None)

    logger.info("Created dataset %s (%d rows, %s)", dataset.id, len(df), file_format)
    return dataset


def add_version(
    dataset: Dataset, df: pd.DataFrame, parent: DatasetVersion | None
) -> DatasetVersion:
    """Store `df` as the dataset's next version and make it the current one.

    Must be called inside a transaction.
    """
    latest = dataset.versions.aggregate(latest=Max("version_no"))["latest"] or 0
    version_no = latest + 1
    version = DatasetVersion(
        dataset=dataset,
        version_no=version_no,
        parent=parent,
        row_count=len(df),
        columns=file_io.infer_column_kinds(df),
    )
    version.data_file.name = file_io.save_parquet(
        df, f"datasets/{dataset.id}/versions/v{version_no}.parquet"
    )
    version.save()

    dataset.current_version = version
    dataset.save(update_fields=["current_version"])
    return version


def get_rows(dataset: Dataset, page: int, page_size: int) -> dict:
    """Return one page of the dataset's current version.

    `changed` lists [row, column] positions (relative to this page) whose value differs
    from the parent version, so the UI can highlight the latest replacements.
    """
    version = dataset.current_version
    offset = (page - 1) * page_size
    result = file_io.read_page(version.data_file.name, offset, page_size)
    changed = _changed_cells(version.parent, result, offset, page_size) if version.parent else []
    return {
        "version": version.version_no,
        "page": page,
        "page_size": page_size,
        "total_rows": result.total_rows,
        "total_pages": math.ceil(result.total_rows / page_size),
        "columns": result.columns,
        "rows": result.rows,
        "changed": changed,
    }


def _changed_cells(
    parent: DatasetVersion, page: file_io.Page, offset: int, page_size: int
) -> list[list[int]]:
    previous = file_io.read_page(parent.data_file.name, offset, page_size)
    previous_index = {name: i for i, name in enumerate(previous.columns)}
    changed = []
    for row_no, (row, previous_row) in enumerate(zip(page.rows, previous.rows, strict=False)):
        for col_no, name in enumerate(page.columns):
            prev_col = previous_index.get(name)
            if prev_col is None or row[col_no] != previous_row[prev_col]:
                changed.append([row_no, col_no])
    return changed
