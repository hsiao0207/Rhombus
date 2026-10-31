"""
Use case for extraction: copy pieces of one column into new columns, using a regex with
named groups that the LLM writes from a plain-language description, such as "extract
the email domain" or "split Name into first and last name".

Like find-and-replace, the LLM writes a rule once and code applies it to every row: one
LLM call whatever the file size, and the same result every time, so apply simply re-runs
the stored pattern. Also like it, a preview scans the first `PREVIEW_ROW_LIMIT` rows
(estimates on larger datasets), and an unusable pattern is sent back to the LLM to be
fixed. Each cell contributes its first match; the source column is never modified.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, replace

import pandas as pd
from django.conf import settings

from datasets.exceptions import PatternGenerationFailed, UnknownColumns
from datasets.models import Dataset, Transformation
from datasets.services import file_io, llm, regex_engine

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExtractionPreview:
    transformation: Transformation
    samples: list[regex_engine.ExtractSample]


@dataclass(frozen=True)
class GeneratedExtraction:
    suggestion: llm.ExtractSuggestion
    column: str
    # [{"group": ..., "column": ...}] in pattern order. A list, not a dict: PostgreSQL's
    # jsonb does not keep key order, and the new columns must keep theirs.
    new_columns: list[dict[str, str]]
    result: regex_engine.ExtractResult
    attempts: int


def preview_extraction(
    dataset: Dataset, *, instruction: str, column: str | None = None
) -> ExtractionPreview:
    """Ask the LLM for an extraction pattern matching `instruction`, then preview it."""
    version = dataset.current_version
    names = [c["name"] for c in version.columns]
    if column is not None and column not in names:
        raise UnknownColumns(details={"unknown": [column], "available": names})

    df = file_io.read_head(version.data_file.name, settings.PREVIEW_ROW_LIMIT)
    generated = generate_extraction(
        df,
        version.columns,
        instruction=instruction,
        column=column,
        generator=llm.get_regex_generator(),
    )
    transformation = Transformation.objects.create(
        dataset=dataset,
        source_version=version,
        kind=Transformation.Kind.EXTRACT,
        instruction=instruction,
        explanation=generated.suggestion.explanation,
        pattern=generated.suggestion.pattern,
        flags=generated.suggestion.flags,
        columns=[generated.column],
        params={"source_column": generated.column, "new_columns": generated.new_columns},
        stats={**generated.result.stats, "total_rows": version.row_count},
    )
    return ExtractionPreview(transformation=transformation, samples=generated.result.samples)


def generate_extraction(
    df: pd.DataFrame,
    column_kinds: list[dict],
    *,
    instruction: str,
    column: str | None,
    generator: llm.RegexGenerator,
) -> GeneratedExtraction:
    """Get an extraction pattern from the LLM and run it over `df`, retrying with
    feedback when the pattern is unusable or matches nothing. A column chosen by the
    user takes precedence over the LLM's choice."""
    request = llm.RegexRequest(
        instruction=instruction, columns=llm.column_context(df, column_kinds)
    )
    names = [c["name"] for c in column_kinds]
    max_attempts = settings.LLM_MAX_ATTEMPTS

    for attempt in range(1, max_attempts + 1):
        suggestion = generator.suggest_extraction(request)
        source = column or suggestion.column
        if source not in names:
            problem = (
                f"There is no column named {suggestion.column!r}. Use one of the exact "
                "column names provided."
            )
        else:
            try:
                compiled = regex_engine.compile_extract_pattern(
                    suggestion.pattern, suggestion.flags
                )
                new_columns = _new_columns(source, regex_engine.named_groups(compiled), names)
                extractor = _extractor(
                    compiled,
                    new_columns,
                    timeout_seconds=settings.REGEX_TIMEOUT_SECONDS,
                    sample_size=settings.PREVIEW_SAMPLE_SIZE,
                )
                extractor.process(df[source])
            except regex_engine.PATTERN_ERRORS as exc:
                problem = exc.message
            else:
                if extractor.result.rows_matched > 0 or attempt == max_attempts:
                    return GeneratedExtraction(
                        suggestion=suggestion,
                        column=source,
                        new_columns=new_columns,
                        result=extractor.result,
                        attempts=attempt,
                    )
                problem = (
                    f"The pattern matched nothing in the {source!r} column. Compare it with "
                    "the sample values and adjust it to the formats actually present in the "
                    "data."
                )

        logger.info("LLM extraction attempt %d/%d rejected: %s", attempt, max_attempts, problem)
        request = replace(request, previous=suggestion, feedback=problem)

    raise PatternGenerationFailed(
        details={"pattern": suggestion.pattern, "reason": problem, "attempts": max_attempts}
    )


def column_inserter(
    transformation: Transformation,
) -> tuple[Callable[[pd.DataFrame], pd.DataFrame], regex_engine.Extractor]:
    """Return a batch function that inserts the extracted columns right after the source,
    and the extractor whose `result` holds the statistics over every row."""
    source = transformation.params["source_column"]
    extractor = _extractor(
        regex_engine.compile_extract_pattern(transformation.pattern, transformation.flags),
        transformation.params["new_columns"],
        timeout_seconds=settings.REGEX_APPLY_TIMEOUT_SECONDS,
        sample_size=0,
    )

    def insert_columns(batch: pd.DataFrame) -> pd.DataFrame:
        extracted = extractor.process(batch[source])
        position = batch.columns.get_loc(source) + 1
        for offset, name in enumerate(extracted.columns):
            batch.insert(position + offset, name, extracted[name])
        return batch

    return insert_columns, extractor


def _extractor(compiled, new_columns, *, timeout_seconds, sample_size) -> regex_engine.Extractor:
    return regex_engine.Extractor(
        compiled,
        {entry["group"]: entry["column"] for entry in new_columns},
        timeout_seconds=timeout_seconds,
        cell_timeout_seconds=settings.REGEX_CELL_TIMEOUT_SECONDS,
        sample_size=sample_size,
    )


def _new_columns(source: str, groups: list[str], existing: list[str]) -> list[dict[str, str]]:
    """Name each group's column "<source>_<group>", avoiding names already in use."""
    taken = set(existing)
    new_columns = []
    for group in groups:
        base = name = f"{source}_{group}"
        suffix = 2
        while name in taken:
            name = f"{base}_{suffix}"
            suffix += 1
        taken.add(name)
        new_columns.append({"group": group, "column": name})
    return new_columns
