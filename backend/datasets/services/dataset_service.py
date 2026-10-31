"""
Use cases for datasets: creating one from an upload, adding versions, reading rows and
deleting expired datasets.

Views stay thin and delegate here; this module orchestrates validation, parsing,
storage and persistence, while `file_io` handles the raw file formats.
"""

import logging
import math
from datetime import timedelta

from django.conf import settings
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

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
    # first; a file that fails to parse then leaves nothing in the database. The upload
    # itself is not kept: version 1 holds all of its data.
    dataset = Dataset(original_name=upload.name, file_format=file_format, file_size=upload.size)
    table = file_io.store_upload(upload, file_format, version_path(dataset, 1))

    with transaction.atomic():
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


DATASETS_DIR = "datasets"


def dataset_dir(dataset_id) -> str:
    """Storage "directory" holding every file of one dataset."""
    return f"{DATASETS_DIR}/{dataset_id}"


def version_path(dataset: Dataset, version_no: int) -> str:
    return f"{dataset_dir(dataset.id)}/versions/v{version_no}.parquet"


def delete_expired_datasets(*, older_than: timedelta) -> tuple[int, int]:
    """Delete datasets uploaded more than `older_than` ago, with their files.

    Also removes leftover dataset directories that no row refers to (for example from
    an upload that failed after its data was written), once their files are equally
    old, so uploads still in progress are never touched. Returns how many datasets and
    leftover directories were removed.
    """
    cutoff = timezone.now() - older_than
    expired = list(Dataset.objects.filter(created_at__lt=cutoff).values_list("id", flat=True))
    for dataset_id in expired:
        # Rows first: if deleting files then fails, what remains is unreferenced files,
        # which the sweep below removes later, never a row pointing at missing data.
        Dataset.objects.filter(pk=dataset_id).delete()
        file_io.delete_tree(dataset_dir(dataset_id))

    existing = {str(pk) for pk in Dataset.objects.values_list("id", flat=True)}
    leftovers = 0
    for name in file_io.list_dirs(DATASETS_DIR):
        if name in existing:
            continue
        modified = file_io.latest_modified(dataset_dir(name))
        if modified is None or modified < cutoff:
            file_io.delete_tree(dataset_dir(name))
            leftovers += 1

    if expired or leftovers:
        logger.info("Deleted %d expired datasets and %d leftover dirs", len(expired), leftovers)
    return len(expired), leftovers


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
