"""
LLM integration for turning natural language into regex.

Callers use `get_regex_generator()` and the types re-exported here, never a provider
module directly, so the provider can be swapped and tests can substitute a fake.
"""

import functools
import os

from django.conf import settings

from datasets.exceptions import LLMNotConfigured
from datasets.services.llm.base import (
    ColumnContext,
    RegexGenerator,
    RegexRequest,
    RegexSuggestion,
)

__all__ = [
    "ColumnContext",
    "RegexGenerator",
    "RegexRequest",
    "RegexSuggestion",
    "get_regex_generator",
]


def get_regex_generator() -> RegexGenerator:
    """Return the configured generator. Tests replace this function with a fake."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise LLMNotConfigured("Set ANTHROPIC_API_KEY to enable natural-language patterns.")
    return _claude_generator()


@functools.cache
def _claude_generator() -> RegexGenerator:
    # Imported lazily so the anthropic package is only loaded when the LLM is used.
    from datasets.services.llm.claude import ClaudeRegexGenerator

    # Cached so the HTTP connection pool is reused across requests.
    return ClaudeRegexGenerator(
        model=settings.LLM_MODEL,
        effort=settings.LLM_EFFORT,
        timeout_seconds=settings.LLM_TIMEOUT_SECONDS,
    )
