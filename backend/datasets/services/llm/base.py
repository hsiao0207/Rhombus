"""
Provider-neutral contract for turning a natural-language description into a regex.

The service layer depends only on `RegexGenerator`; `claude.py` implements it with the
Anthropic API and tests substitute a fake.
"""

from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import BaseModel, Field

Flag = Literal["IGNORECASE", "MULTILINE", "DOTALL"]


class RegexSuggestion(BaseModel):
    # The docstring and field descriptions are sent to the model as part of the JSON schema.
    """A regex-based find-and-replace that implements the user's request."""

    pattern: str = Field(
        description="Python `re`-compatible regular expression that matches what the user "
        "described. It must never match empty text."
    )
    flags: list[Flag] = Field(description="Regex flags to apply. Usually empty.")
    replacement: str | None = Field(
        description="Replacement value if the user stated one, using Python template syntax "
        "(\\1 or \\g<name> for groups, \\\\ for a literal backslash). null if not stated."
    )
    columns: list[str] = Field(
        description="Exact names of the columns the user referred to, from the provided list. "
        "Empty if the user did not restrict the columns."
    )
    explanation: str = Field(
        description="One short sentence for the end user describing what the pattern "
        "matches, written in the same language as the user's request."
    )


@dataclass(frozen=True)
class ColumnContext:
    name: str
    kind: str
    samples: list[str]


@dataclass(frozen=True)
class RegexRequest:
    instruction: str
    columns: list[ColumnContext]
    # Set on self-correction retries: the rejected answer and why it was rejected.
    previous: RegexSuggestion | None = None
    feedback: str | None = None


class RegexGenerator(Protocol):
    def suggest(self, request: RegexRequest) -> RegexSuggestion: ...
