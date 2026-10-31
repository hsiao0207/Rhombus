"""
Use case for LLM classification: sort the values of one column into categories and add
the result as a new column next to it. The original column is never modified.

Unlike find-and-replace, where the LLM writes a regex once and code applies it to every
row, here the LLM judges each distinct value, because categories depend on meaning (a
complaint and a question may share no keywords). That has two consequences:
- Cost grows with the number of distinct values, so a column may have at most
  `MAX_CLASSIFY_VALUES` of them. Values are sent in batches, several batches at a time.
- The LLM may answer differently on every call, so the preview classifies every
  distinct value and stores the value -> category mapping. Apply only looks values up
  in that mapping: the result is exactly what was previewed, and the LLM is not called
  again.
"""

import logging
from collections import defaultdict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import pandas as pd
from django.conf import settings

from datasets.exceptions import (
    LLMBadOutput,
    NothingToClassify,
    TooManyCategories,
    TooManyValues,
    UnknownColumns,
)
from datasets.models import Dataset, Transformation
from datasets.services import file_io, llm
from datasets.services.regex_engine import CellChange

logger = logging.getLogger(__name__)

OTHER = "Other"
# For the rare value the LLM still leaves unlabeled after a retry.
UNCLASSIFIED = "Unclassified"
# Distinct values shown to the LLM when it decides or proposes the categories.
PLAN_SAMPLE_VALUES = 20


@dataclass(frozen=True)
class ClassificationPreview:
    transformation: Transformation
    # Examples as before -> after pairs: the value and the category it was given.
    samples: list[CellChange]


@dataclass
class _ColumnValues:
    counts: dict[str, int] = field(default_factory=dict)  # distinct value -> rows
    first_rows: dict[str, int] = field(default_factory=dict)  # distinct value -> first row


def preview_classification(dataset: Dataset, *, column: str, instruction: str):
    """Classify every distinct value of `column` and record the result as a preview."""
    version = dataset.current_version
    names = [c["name"] for c in version.columns]
    if column not in names:
        raise UnknownColumns(details={"unknown": [column], "available": names})

    values = _distinct_values(version.data_file.name, column)
    if not values.counts:
        raise NothingToClassify()

    classifier = llm.get_value_classifier()
    distinct = list(values.counts)
    plan = classifier.plan(
        llm.ClassifyPlanRequest(
            instruction=instruction,
            column=column,
            samples=[_truncate(value) for value in distinct[:PLAN_SAMPLE_VALUES]],
        )
    )
    categories = _categories(plan.categories)
    mapping = _classify_all(classifier, instruction, categories, distinct)

    transformation = Transformation.objects.create(
        dataset=dataset,
        source_version=version,
        kind=Transformation.Kind.CLASSIFY,
        instruction=instruction,
        explanation=plan.explanation,
        columns=[column],
        params={
            "source_column": column,
            "new_column": _new_column_name(column, names),
            "categories": categories,
            "mapping": mapping,
        },
        stats=_stats(values, mapping, categories, version.row_count),
    )
    return ClassificationPreview(
        transformation=transformation, samples=_samples(values, mapping, column)
    )


def column_adder(transformation: Transformation) -> Callable[[pd.DataFrame], pd.DataFrame]:
    """Return a batch function that adds the category column right after its source."""
    params = transformation.params
    source, new_column, mapping = params["source_column"], params["new_column"], params["mapping"]

    def add_column(batch: pd.DataFrame) -> pd.DataFrame:
        batch.insert(batch.columns.get_loc(source) + 1, new_column, batch[source].map(mapping))
        return batch

    return add_column


def _distinct_values(path: str, column: str) -> _ColumnValues:
    """Count the distinct non-empty values, stopping as soon as there are too many."""
    limit = settings.MAX_CLASSIFY_VALUES
    values = _ColumnValues()
    offset = 0
    for batch in file_io.iter_batches(path, columns=[column]):
        series = batch[column].dropna()
        for value, count in series.value_counts(sort=False).items():
            values.counts[value] = values.counts.get(value, 0) + int(count)
        # drop_duplicates keeps each value's first occurrence, with its row index.
        for row, value in series.drop_duplicates().items():
            values.first_rows.setdefault(value, offset + int(row))
        if len(values.counts) > limit:
            raise TooManyValues(
                f"{column!r} has more than {limit:,} distinct values, the most that can be "
                "classified at once. Choose a column with repeated values, such as a "
                "category, status or short comment field.",
                details={"max_values": limit},
            )
        offset += len(batch)
    return values


def _categories(raw: list[str]) -> list[str]:
    """Clean up the LLM's category list and add the catch-all."""
    categories: list[str] = []
    seen: set[str] = set()
    for name in raw:
        name = name.strip()
        key = name.casefold()
        if name and key not in seen and key != OTHER.casefold():
            seen.add(key)
            categories.append(name)
    if not categories:
        raise LLMBadOutput("The language model did not return any categories.")
    if len(categories) > settings.MAX_CLASSIFY_CATEGORIES:
        raise TooManyCategories(
            f"Use at most {settings.MAX_CLASSIFY_CATEGORIES} categories.",
            details={"categories": categories},
        )
    return [*categories, OTHER]


def _classify_all(
    classifier: llm.ValueClassifier, instruction: str, categories: list[str], values: list[str]
) -> dict[str, str]:
    size = settings.CLASSIFY_BATCH_SIZE
    batches = [values[start : start + size] for start in range(0, len(values), size)]
    # Each batch is an independent HTTP request, so threads overlap their waiting time.
    with ThreadPoolExecutor(max_workers=settings.CLASSIFY_CONCURRENCY) as pool:
        results = pool.map(
            lambda batch: _classify_batch(classifier, instruction, categories, batch), batches
        )
        mapping: dict[str, str] = {}
        for result in results:
            mapping.update(result)
    logger.info("Classified %d distinct values in %d batches", len(values), len(batches))
    return mapping


def _classify_batch(
    classifier: llm.ValueClassifier, instruction: str, categories: list[str], values: list[str]
) -> dict[str, str]:
    """Classify one batch; values the LLM skips or mislabels get one more try."""
    labels = _ask(classifier, instruction, categories, values)
    missing = [index for index in range(len(values)) if index not in labels]
    if missing:
        retry = _ask(classifier, instruction, categories, [values[i] for i in missing])
        for retry_index, index in enumerate(missing):
            if retry_index in retry:
                labels[index] = retry[retry_index]
    return {value: labels.get(index, UNCLASSIFIED) for index, value in enumerate(values)}


def _ask(
    classifier: llm.ValueClassifier, instruction: str, categories: list[str], values: list[str]
) -> dict[int, str]:
    """Return {value index: category}, keeping only valid ids and known categories."""
    response = classifier.classify(
        llm.ClassifyBatchRequest(
            instruction=instruction,
            categories=categories,
            values=[_truncate(value) for value in values],
        )
    )
    canonical = {category.casefold(): category for category in categories}
    return {
        label.id: canonical[label.category.casefold()]
        for label in response.labels
        if 0 <= label.id < len(values) and label.category.casefold() in canonical
    }


def _new_column_name(column: str, existing: list[str]) -> str:
    base = name = f"{column}_category"
    suffix = 2
    while name in existing:
        name = f"{base}_{suffix}"
        suffix += 1
    return name


def _stats(
    values: _ColumnValues, mapping: dict[str, str], categories: list[str], total_rows: int
) -> dict:
    rows = dict.fromkeys([*categories, UNCLASSIFIED], 0)
    for value, count in values.counts.items():
        rows[mapping[value]] += count
    if not rows[UNCLASSIFIED]:
        del rows[UNCLASSIFIED]
    return {
        "categories": rows,
        "distinct_values": len(values.counts),
        "rows_classified": sum(values.counts.values()),
        "total_rows": total_rows,
    }


def _samples(values: _ColumnValues, mapping: dict[str, str], column: str) -> list[CellChange]:
    """Pick examples round-robin across categories so every category is represented."""
    by_category: dict[str, list[str]] = defaultdict(list)
    for value in sorted(values.counts, key=values.first_rows.__getitem__):
        by_category[mapping[value]].append(value)

    picked: list[str] = []
    queues = list(by_category.values())
    while queues and len(picked) < settings.PREVIEW_SAMPLE_SIZE:
        for queue in queues:
            if queue and len(picked) < settings.PREVIEW_SAMPLE_SIZE:
                picked.append(queue.pop(0))
        queues = [queue for queue in queues if queue]

    picked.sort(key=values.first_rows.__getitem__)
    return [
        CellChange(row=values.first_rows[value], column=column, before=value, after=mapping[value])
        for value in picked
    ]


def _truncate(value: str) -> str:
    limit = settings.CLASSIFY_MAX_VALUE_CHARS
    return value if len(value) <= limit else value[:limit] + "…"
