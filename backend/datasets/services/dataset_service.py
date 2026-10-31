"""
Use cases for datasets: creating one from an upload, adding versions and reading rows.

Views stay thin and delegate here; this module orchestrates validation, parsing,
storage and persistence, while `file_io` handles the raw file formats.
"""

import logging
import math

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
    _check_size(
        upload.size,
        settings.MAX_UPLOAD_SIZE_MB,
        settings.MAX_UPLOAD_SIZE_BYTES,
        f"Files must be {settings.MAX_UPLOAD_SIZE_MB} MB or smaller.",
    )
    file_format = file_io.detect_format(upload.name)
    if file_format == Dataset.FileFormat.XLSX:
        _check_size(
            upload.size,
            settings.MAX_EXCEL_UPLOAD_SIZE_MB,
            settings.MAX_EXCEL_UPLOAD_SIZE_BYTES,
            f"Excel files must be {settings.MAX_EXCEL_UPLOAD_SIZE_MB} MB or smaller. "
            "Save larger files as CSV.",
        )

    # The id exists before saving, so the parsed data can be written to its final path
    # first; a file that fails to parse then leaves nothing in the database.
    dataset = Dataset(original_name=upload.name, file_format=file_format, file_size=upload.size)
    table = file_io.store_upload(upload, file_format, version_path(dataset, 1))

    with transaction.atomic():
        upload.seek(0)
        dataset.original_file.save(upload.name, upload, save=False)
        dataset.save()
        add_version(dataset, 1, table, parent=None)

    logger.info("Created dataset %s (%d rows, %s)", dataset.id, table.row_count, file_format)
    return dataset


def _check_size(size: int, max_mb: int, max_bytes: int, message: str) -> None:
    if size > max_bytes:
        raise FileTooLarge(message, details={"max_size_mb": max_mb, "size_bytes": size})


def next_version_no(dataset: Dataset) -> int:
    """Must be called while holding a lock on the dataset (see `transformation_service`)."""
    return (dataset.versions.aggregate(latest=Max("version_no"))["latest"] or 0) + 1


def version_path(dataset: Dataset, version_no: int) -> str:
    return f"datasets/{dataset.id}/versions/v{version_no}.parquet"


def add_version(
    dataset: Dataset,
    version_no: int,
    table: file_io.StoredTable,
    parent: DatasetVersion | None,
) -> DatasetVersion:
    """Record an already-written Parquet file as a version and make it the current one.

    Must be called inside a transaction.
    """
    version = DatasetVersion(
        dataset=dataset,
        version_no=version_no,
        parent=parent,
        row_count=table.row_count,
        columns=table.columns,
    )
    version.data_file.name = table.path
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
