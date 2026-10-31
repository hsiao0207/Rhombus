"""
Safe regex replacement and extraction over DataFrame columns.

This module is framework-free: it takes DataFrames and returns new ones plus statistics.
`Replacer` (find and replace) and `Extractor` (copy named groups into new columns)
process a dataset batch by batch so large files never have to fit in memory;
`replace_in_columns` is the one-shot form for a single DataFrame.

Safety:
- Uses the `regex` package instead of `re`. It avoids many catastrophic-backtracking cases
  on its own and supports a per-call `timeout` (ReDoS protection for untrusted /
  LLM-written patterns). Two limits apply: each cell gets at most `cell_timeout_seconds`,
  so a pathological pattern fails fast, and the whole operation gets `timeout_seconds`,
  which callers scale to the amount of data (a short preview vs. a full apply).
- Patterns that can match empty text are rejected: replacing them would insert the
  replacement between every character, which is almost always a mistake.

Performance: each column is processed per *unique* value within a batch and the results
are mapped back, so a column with many repeated values costs few regex calls.
"""

import time
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import regex

from datasets.exceptions import (
    InvalidGroups,
    InvalidRegex,
    InvalidReplacement,
    PatternMatchesEmpty,
    RegexTimeout,
)

FLAGS = {
    "IGNORECASE": regex.IGNORECASE,
    "MULTILINE": regex.MULTILINE,
    "DOTALL": regex.DOTALL,
}

# Errors caused by an unusable pattern. When the pattern came from the LLM these are fed
# back to it so it can correct itself; for hand-written patterns they go to the user.
PATTERN_ERRORS = (
    InvalidRegex,
    PatternMatchesEmpty,
    InvalidReplacement,
    InvalidGroups,
    RegexTimeout,
)

MAX_EXTRACT_GROUPS = 10


@dataclass(frozen=True)
class CellChange:
    row: int
    column: str
    before: str
    after: str


@dataclass
class ReplaceResult:
    data: pd.DataFrame | None = None  # Only set by `replace_in_columns`.
    matches: dict[str, int] = field(default_factory=dict)
    cells_changed: dict[str, int] = field(default_factory=dict)
    rows_affected: int = 0
    rows_scanned: int = 0
    samples: list[CellChange] = field(default_factory=list)

    @property
    def stats(self) -> dict:
        return {
            "total_matches": sum(self.matches.values()),
            "total_cells_changed": sum(self.cells_changed.values()),
            "rows_affected": self.rows_affected,
            "rows_scanned": self.rows_scanned,
            "columns": {
                name: {"matches": self.matches[name], "cells_changed": self.cells_changed[name]}
                for name in self.matches
            },
        }


def compile_pattern(pattern: str, flags: list[str] | None = None) -> regex.Pattern:
    """Compile and sanity-check a user- or LLM-supplied pattern."""
    flag_value = 0
    for name in flags or []:
        flag_value |= FLAGS[name]
    try:
        compiled = regex.compile(pattern, flag_value)
    except regex.error as exc:
        raise InvalidRegex(
            f"Invalid regular expression: {exc.msg}.",
            details={"reason": exc.msg, "position": exc.pos},
        ) from None
    if compiled.search("") is not None:
        raise PatternMatchesEmpty()
    return compiled


def compile_extract_pattern(pattern: str, flags: list[str] | None = None) -> regex.Pattern:
    """Compile a pattern for extraction: it needs 1 to MAX_EXTRACT_GROUPS named groups."""
    compiled = compile_pattern(pattern, flags)
    groups = named_groups(compiled)
    if not groups:
        raise InvalidGroups()
    if len(groups) > MAX_EXTRACT_GROUPS:
        raise InvalidGroups(
            f"Use at most {MAX_EXTRACT_GROUPS} named groups.", details={"groups": groups}
        )
    return compiled


def named_groups(compiled: regex.Pattern) -> list[str]:
    """Named groups in pattern order. A name reused in several alternatives (allowed by
    the `regex` package, e.g. one `year` group per date format) counts once."""
    return sorted(compiled.groupindex, key=compiled.groupindex.__getitem__)


class Replacer:
    """Replaces every match of `compiled` in `columns`, one DataFrame batch at a time.

    Statistics and samples accumulate in `result` across batches; sample rows are
    numbered across the whole dataset, not within a batch.
    """

    def __init__(
        self,
        compiled: regex.Pattern,
        replacement: str,
        columns: list[str],
        *,
        timeout_seconds: float,
        cell_timeout_seconds: float = 1.0,
        sample_size: int = 20,
    ) -> None:
        self._compiled = compiled
        self._replacement = replacement
        self._columns = columns
        self._deadline = time.monotonic() + timeout_seconds
        self._cell_timeout = cell_timeout_seconds
        self._sample_size = sample_size
        self.result = ReplaceResult(
            matches=dict.fromkeys(columns, 0), cells_changed=dict.fromkeys(columns, 0)
        )

    def process(self, df: pd.DataFrame) -> pd.DataFrame:
        """Return a copy of `df` with the replacement applied to the target columns."""
        result = self.result
        updated = df.copy()
        for name in self._columns:
            mapping, matches = self._replace_unique_values(df[name])
            updated[name] = df[name].map(mapping)
            result.matches[name] += matches
            result.cells_changed[name] += int(_changed_mask(df[name], updated[name]).sum())

        changed = pd.DataFrame(
            {name: _changed_mask(df[name], updated[name]) for name in self._columns}
        ).to_numpy()
        if changed.size:
            result.rows_affected += int(changed.any(axis=1).sum())
        # np.argwhere yields (row, column) pairs in row-major order: earliest rows first.
        for row, col in np.argwhere(changed)[: self._sample_size - len(result.samples)]:
            name = self._columns[col]
            result.samples.append(
                CellChange(
                    row=result.rows_scanned + int(row),
                    column=name,
                    before=df[name].iat[row],
                    after=updated[name].iat[row],
                )
            )
        result.rows_scanned += len(df)
        return updated

    def _replace_unique_values(self, series: pd.Series) -> tuple[dict[str, str], int]:
        """Run the substitution once per distinct value; return {old: new} and match count."""
        counts = series.dropna().value_counts(sort=False)
        mapping: dict[str, str] = {}
        total_matches = 0
        for value, frequency in counts.items():
            remaining = self._deadline - time.monotonic()
            if remaining <= 0:
                raise RegexTimeout()
            new_value, n = _substitute(
                self._compiled, self._replacement, value, min(remaining, self._cell_timeout)
            )
            mapping[value] = new_value
            total_matches += n * int(frequency)
        return mapping, total_matches


def replace_in_columns(
    df: pd.DataFrame,
    compiled: regex.Pattern,
    replacement: str,
    columns: list[str],
    *,
    timeout_seconds: float,
    cell_timeout_seconds: float = 1.0,
    sample_size: int = 20,
) -> ReplaceResult:
    """Replace every match of `compiled` in `columns` of one DataFrame.

    Returns the statistics with the new DataFrame in `result.data`.
    """
    replacer = Replacer(
        compiled,
        replacement,
        columns,
        timeout_seconds=timeout_seconds,
        cell_timeout_seconds=cell_timeout_seconds,
        sample_size=sample_size,
    )
    data = replacer.process(df)
    replacer.result.data = data
    return replacer.result


@dataclass(frozen=True)
class ExtractSample:
    row: int
    value: str
    parts: dict[str, str | None]  # new column -> extracted text


@dataclass
class ExtractResult:
    extracted: dict[str, int] = field(default_factory=dict)  # new column -> rows with a value
    rows_matched: int = 0
    rows_scanned: int = 0
    samples: list[ExtractSample] = field(default_factory=list)

    @property
    def stats(self) -> dict:
        return {
            "rows_matched": self.rows_matched,
            "rows_scanned": self.rows_scanned,
            "columns": dict(self.extracted),
        }


class Extractor:
    """Copies the named groups of the first match in each cell into new columns, one
    batch at a time. `columns` maps each group name to its new column, in output order.

    A cell without a match, or a group that captured nothing, gives an empty value.
    """

    def __init__(
        self,
        compiled: regex.Pattern,
        columns: dict[str, str],
        *,
        timeout_seconds: float,
        cell_timeout_seconds: float = 1.0,
        sample_size: int = 20,
    ) -> None:
        self._compiled = compiled
        self._columns = columns
        self._deadline = time.monotonic() + timeout_seconds
        self._cell_timeout = cell_timeout_seconds
        self._sample_size = sample_size
        self.result = ExtractResult(extracted=dict.fromkeys(columns.values(), 0))

    def process(self, values: pd.Series) -> pd.DataFrame:
        """Return the new columns for one batch of the source column, on its index."""
        result = self.result
        found = self._search_unique_values(values)
        extracted = pd.DataFrame(index=values.index)
        for index, column in enumerate(self._columns.values()):
            parts = {value: groups[index] for value, groups in found.items() if groups}
            extracted[column] = values.map(parts)
            result.extracted[column] += int(extracted[column].notna().sum())

        matched = values.isin([value for value, groups in found.items() if groups])
        result.rows_matched += int(matched.sum())
        wanted = self._sample_size - len(result.samples)
        for position in np.flatnonzero(matched.to_numpy())[: max(wanted, 0)]:
            result.samples.append(
                ExtractSample(
                    row=result.rows_scanned + int(position),
                    value=values.iat[position],
                    parts={
                        column: None if pd.isna(part) else part
                        for column, part in extracted.iloc[position].items()
                    },
                )
            )
        result.rows_scanned += len(values)
        return extracted

    def _search_unique_values(self, values: pd.Series) -> dict[str, tuple | None]:
        """{value: captured text per group, or None when nothing matched}."""
        groups = list(self._columns)
        found: dict[str, tuple | None] = {}
        for value in values.dropna().unique():
            remaining = self._deadline - time.monotonic()
            if remaining <= 0:
                raise RegexTimeout()
            try:
                match = self._compiled.search(value, timeout=min(remaining, self._cell_timeout))
            except TimeoutError:
                raise RegexTimeout() from None
            found[value] = None if match is None else tuple(match.group(g) or None for g in groups)
        return found


def _substitute(
    compiled: regex.Pattern, replacement: str, value: str, timeout: float
) -> tuple[str, int]:
    try:
        return compiled.subn(replacement, value, timeout=timeout)
    except TimeoutError:
        raise RegexTimeout() from None
    except (regex.error, IndexError) as exc:
        raise InvalidReplacement(details={"reason": str(exc)}) from None


def _changed_mask(before: pd.Series, after: pd.Series) -> pd.Series:
    return before.notna() & (before != after)
