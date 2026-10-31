"""Grounding for the LLM: each column's name, kind and a few real values."""

import pandas as pd
from django.conf import settings

from datasets.services.llm.base import ColumnContext


def column_context(df: pd.DataFrame, column_kinds: list[dict]) -> list[ColumnContext]:
    """Column names, kinds and a few distinct example values, truncated."""
    context = []
    for column in column_kinds:
        values = df[column["name"]].dropna().drop_duplicates().head(settings.LLM_SAMPLE_VALUES)
        context.append(
            ColumnContext(
                name=column["name"],
                kind=column["kind"],
                samples=[value[:100] for value in values],
            )
        )
    return context
