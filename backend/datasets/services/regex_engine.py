"""
Safe regex replacement over DataFrame columns.

This module is framework-free: it takes a DataFrame and returns a new one plus statistics.

Safety:
- Uses the `regex` package instead of `re`. It avoids many catastrophic-backtracking cases
  on its own and supports a per-call `timeout`, which we use to enforce a total time
  budget for the whole operation (ReDoS protection for untrusted / LLM-written patterns).
- Patterns that can match empty text are rejected: replacing them would insert the
  replacement between every character, which is almost always a mistake.

Performance: each column is processed per *unique* value and the results are mapped
back, so a million-row column with a few hundred distinct values costs a few hundred
regex calls.
"""

import time
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import regex

from datasets.exceptions import InvalidRegex, InvalidReplacement, PatternMatchesEmpty, RegexTimeout

FLAGS = {
    "IGNORECASE": regex.IGNORECASE,
    "MULTILINE": regex.MULTILINE,
    "DOTALL": regex.DOTALL,
}


@dataclass(frozen=True)
class CellChange:
    row: int
    column: str
    before: str
    after: str


@dataclass
class ReplaceResult:
    data: pd.DataFrame
    matches: dict[str, int] = field(default_factory=dict)
    cells_changed: dict[str, int] = field(default_factory=dict)
    rows_affected: int = 0
    samples: list[CellChange] = field(default_factory=list)

    @property
    def stats(self) -> dict:
        return {
            "total_matches": sum(self.matches.values()),
            "total_cells_changed": sum(self.cells_changed.values()),
            "rows_affected": self.rows_affected,
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


def replace_in_columns(
    df: pd.DataFrame,
    compiled: regex.Pattern,
    replacement: str,
    columns: list[str],
    *,
    timeout_seconds: float,
    sample_size: int = 20,
) -> ReplaceResult:
    """Replace every match of `compiled` in `columns`, returning a new DataFrame."""
    deadline = time.monotonic() + timeout_seconds
    result = ReplaceResult(data=df.copy())

    for name in columns:
        original = df[name]
        mapping, matches = _replace_unique_values(original, compiled, replacement, deadline)
        updated = original.map(mapping)
        result.data[name] = updated
        result.matches[name] = matches
        result.cells_changed[name] = int(_changed_mask(original, updated).sum())

    changed = pd.DataFrame(
        {name: _changed_mask(df[name], result.data[name]) for name in columns}
    ).to_numpy()
    result.rows_affected = int(changed.any(axis=1).sum()) if changed.size else 0
    # np.argwhere yields (row, column) pairs in row-major order: earliest rows first.
    for row, col in np.argwhere(changed)[:sample_size]:
        name = columns[col]
        result.samples.append(
            CellChange(
                row=int(row),
                column=name,
                before=df[name].iat[row],
                after=result.data[name].iat[row],
            )
        )
    return result


def _replace_unique_values(
    series: pd.Series, compiled: regex.Pattern, replacement: str, deadline: float
) -> tuple[dict[str, str], int]:
    """Run the substitution once per distinct value; return {old: new} and match count."""
    counts = series.dropna().value_counts(sort=False)
    mapping: dict[str, str] = {}
    total_matches = 0
    for value, frequency in counts.items():
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RegexTimeout()
        try:
            new_value, n = compiled.subn(replacement, value, timeout=remaining)
        except TimeoutError:
            raise RegexTimeout() from None
        except (regex.error, IndexError) as exc:
            raise InvalidReplacement(details={"reason": str(exc)}) from None
        mapping[value] = new_value
        total_matches += n * int(frequency)
    return mapping, total_matches


def _changed_mask(before: pd.Series, after: pd.Series) -> pd.Series:
    return before.notna() & (before != after)
