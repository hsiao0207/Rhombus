"""
Use cases for find-and-replace transformations.

The flow is two-step so users can inspect what will change before committing:
1. `preview` runs the pattern over the current version and records a `Transformation`
   with statistics and sample changes, without modifying any data.
2. `apply` re-runs exactly that transformation and stores the result as a new version.
"""

import logging
from dataclasses import dataclass

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from datasets.exceptions import NoTargetColumns, TransformationConflict, UnknownColumns
from datasets.models import Dataset, Transformation
from datasets.services import dataset_service, file_io, regex_engine

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Preview:
    transformation: Transformation
    samples: list[regex_engine.CellChange]


def preview(
    dataset: Dataset,
    *,
    pattern: str,
    replacement: str,
    flags: list[str],
    columns: list[str] | None = None,
    instruction: str = "",
) -> Preview:
    version = dataset.current_version
    target_columns = _resolve_columns(version.columns, columns)
    compiled = regex_engine.compile_pattern(pattern, flags)

    df = file_io.read_dataframe(version.data_file.name)
    result = regex_engine.replace_in_columns(
        df,
        compiled,
        replacement,
        target_columns,
        timeout_seconds=settings.REGEX_TIMEOUT_SECONDS,
        sample_size=settings.PREVIEW_SAMPLE_SIZE,
    )

    transformation = Transformation.objects.create(
        dataset=dataset,
        source_version=version,
        instruction=instruction,
        pattern=pattern,
        flags=flags,
        replacement=replacement,
        columns=target_columns,
        stats=result.stats,
    )
    return Preview(transformation=transformation, samples=result.samples)


def apply(transformation: Transformation) -> Transformation:
    with transaction.atomic():
        # Lock the dataset so two concurrent applies cannot both build on the same version.
        dataset = Dataset.objects.select_for_update().get(pk=transformation.dataset_id)
        transformation.refresh_from_db()

        if transformation.status == Transformation.Status.APPLIED:
            raise TransformationConflict(
                "ALREADY_APPLIED", "This transformation has already been applied."
            )
        if dataset.current_version_id != transformation.source_version_id:
            raise TransformationConflict(
                "STALE_VERSION",
                "The data has changed since this preview was made. Preview again.",
            )

        source = transformation.source_version
        compiled = regex_engine.compile_pattern(transformation.pattern, transformation.flags)
        result = regex_engine.replace_in_columns(
            file_io.read_dataframe(source.data_file.name),
            compiled,
            transformation.replacement,
            transformation.columns,
            timeout_seconds=settings.REGEX_TIMEOUT_SECONDS,
            sample_size=0,
        )

        transformation.result_version = dataset_service.add_version(
            dataset, result.data, parent=source
        )
        transformation.status = Transformation.Status.APPLIED
        transformation.stats = result.stats
        transformation.applied_at = timezone.now()
        transformation.save()

    logger.info(
        "Applied transformation %s to dataset %s -> v%d",
        transformation.id,
        dataset.id,
        transformation.result_version.version_no,
    )
    return transformation


def _resolve_columns(available: list[dict], requested: list[str] | None) -> list[str]:
    """Validate requested columns; default to every text column."""
    names = [column["name"] for column in available]
    if requested:
        unknown = [name for name in requested if name not in names]
        if unknown:
            raise UnknownColumns(
                details={"unknown": unknown, "available": names},
            )
        return list(dict.fromkeys(requested))  # de-duplicate, keep order

    text_columns = [column["name"] for column in available if column["kind"] == "text"]
    if not text_columns:
        raise NoTargetColumns(details={"available": names})
    return text_columns
