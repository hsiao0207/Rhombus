"""
LLM integration: turning natural language into regex (to replace or extract), and
classifying values.

Callers use `get_regex_generator()`, `get_value_classifier()` and the types re-exported
here, never a provider module directly, so the provider can be swapped and tests can
substitute fakes.
"""

import functools
import os

from django.conf import settings

from datasets.exceptions import LLMNotConfigured
from datasets.services.llm.base import (
    ClassificationBatch,
    ClassificationPlan,
    ClassifyBatchRequest,
    ClassifyPlanRequest,
    ColumnContext,
    ExtractSuggestion,
    RegexGenerator,
    RegexRequest,
    RegexSuggestion,
    ValueClassifier,
    ValueLabel,
)
from datasets.services.llm.context import column_context

__all__ = [
    "ClassificationBatch",
    "ClassificationPlan",
    "ClassifyBatchRequest",
    "ClassifyPlanRequest",
    "ColumnContext",
    "ExtractSuggestion",
    "RegexGenerator",
    "RegexRequest",
    "RegexSuggestion",
    "ValueClassifier",
    "ValueLabel",
    "column_context",
    "get_regex_generator",
    "get_value_classifier",
]


def get_regex_generator() -> RegexGenerator:
    """Return the configured generator. Tests replace this function with a fake."""
    _require_api_key()
    return _claude_generator()


def get_value_classifier() -> ValueClassifier:
    """Return the configured classifier. Tests replace this function with a fake."""
    _require_api_key()
    return _claude_classifier()


def _require_api_key() -> None:
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise LLMNotConfigured("Set ANTHROPIC_API_KEY to enable natural-language features.")


# Imported lazily so the anthropic package is only loaded when the LLM is used, and
# cached so the HTTP connection pool is reused across requests.
@functools.cache
def _claude_generator() -> RegexGenerator:
    from datasets.services.llm.claude import ClaudeRegexGenerator

    return ClaudeRegexGenerator(
        model=settings.LLM_MODEL,
        effort=settings.LLM_EFFORT,
        timeout_seconds=settings.LLM_TIMEOUT_SECONDS,
    )


@functools.cache
def _claude_classifier() -> ValueClassifier:
    from datasets.services.llm.claude import ClaudeValueClassifier

    return ClaudeValueClassifier(
        model=settings.LLM_CLASSIFY_MODEL,
        effort=settings.LLM_CLASSIFY_EFFORT,
        timeout_seconds=settings.LLM_TIMEOUT_SECONDS,
    )
