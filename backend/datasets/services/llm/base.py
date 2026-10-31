"""
Provider-neutral contracts for the LLM features: turning a natural-language description
into a regex (`RegexGenerator`) and sorting values into categories (`ValueClassifier`).

The service layer depends only on these protocols; `claude.py` implements them with the
Anthropic API and tests substitute fakes.
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
        description="One short sentence in English for the end user describing what the "
        "pattern matches."
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


class ClassificationPlan(BaseModel):
    """The categories to sort a column's values into."""

    categories: list[str] = Field(
        description="Category names. If the user listed categories, exactly those, in the "
        "user's order and spelling. Otherwise 2 to 6 short names that fit the sample values. "
        "Never include a catch-all such as 'Other'; one is added automatically."
    )
    explanation: str = Field(
        description="One short sentence in English for the end user describing how the "
        "values will be classified."
    )


class ValueLabel(BaseModel):
    id: int
    category: str


class ClassificationBatch(BaseModel):
    labels: list[ValueLabel]


@dataclass(frozen=True)
class ClassifyPlanRequest:
    instruction: str
    column: str
    samples: list[str]


@dataclass(frozen=True)
class ClassifyBatchRequest:
    instruction: str
    categories: list[str]
    # A value's id is its index in this list.
    values: list[str]


class ValueClassifier(Protocol):
    def plan(self, request: ClassifyPlanRequest) -> ClassificationPlan: ...

    def classify(self, request: ClassifyBatchRequest) -> ClassificationBatch: ...
