"""
Unit tests for `ClaudeRegexGenerator` and `ClaudeValueClassifier` using a fake Anthropic
client (no network calls): request contents, refusal and unusable-output handling, and
API error mapping.
"""

from types import SimpleNamespace

import anthropic
import httpx2
import pytest

from datasets.exceptions import LLMBadOutput, LLMRefused, LLMUnavailable
from datasets.services.llm import (
    ClassificationPlan,
    ClassifyBatchRequest,
    ClassifyPlanRequest,
    ColumnContext,
    ExtractSuggestion,
    RegexRequest,
    RegexSuggestion,
    ValueLabel,
)
from datasets.services.llm.claude import ClaudeRegexGenerator, ClaudeValueClassifier, _batch_format
from datasets.services.llm.prompts import build_user_message

REQUEST = RegexRequest(
    instruction="find emails",
    columns=[ColumnContext(name="Email", kind="text", samples=["a@b.com"])],
)
SUGGESTION = RegexSuggestion(
    pattern=r"\S+@\S+", flags=[], replacement=None, columns=["Email"], explanation="Emails."
)


def response(stop_reason="end_turn", parsed_output=SUGGESTION):
    return SimpleNamespace(
        model="claude-opus-5-5",
        stop_reason=stop_reason,
        parsed_output=parsed_output,
        usage=SimpleNamespace(input_tokens=10, output_tokens=5),
        _request_id="req_test",
    )


class FakeClient:
    def __init__(self, result):
        self.calls = []

        def parse(**kwargs):
            self.calls.append(kwargs)
            if isinstance(result, Exception):
                raise result
            return result

        self.beta = SimpleNamespace(messages=SimpleNamespace(parse=parse))
        self.messages = SimpleNamespace(parse=parse)


def generator(result):
    client = FakeClient(result)
    return ClaudeRegexGenerator(
        model="claude-opus-5-5", effort="medium", timeout_seconds=5, client=client
    ), client


def test_returns_parsed_output_and_sends_expected_request():
    gen, client = generator(response())

    assert gen.suggest(REQUEST) == SUGGESTION
    call = client.calls[0]
    assert call["model"] == "claude-opus-5-5"
    assert call["output_format"] is RegexSuggestion
    assert call["output_config"] == {"effort": "medium"}
    assert call["fallbacks"] == "default"
    assert "<request>\nfind emails\n</request>" in call["messages"][0]["content"]


def test_refusal_raises():
    gen, _ = generator(response(stop_reason="refusal", parsed_output=None))
    with pytest.raises(LLMRefused):
        gen.suggest(REQUEST)


@pytest.mark.parametrize("stop_reason,parsed", [("max_tokens", SUGGESTION), ("end_turn", None)])
def test_unusable_output_raises(stop_reason, parsed):
    gen, _ = generator(response(stop_reason=stop_reason, parsed_output=parsed))
    with pytest.raises(LLMBadOutput):
        gen.suggest(REQUEST)


def _status_error(cls, status):
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    return cls("error", response=httpx2.Response(status, request=request), body=None)


@pytest.mark.parametrize(
    "error",
    [
        anthropic.APIConnectionError(request=httpx2.Request("POST", "https://x")),
        anthropic.APITimeoutError(request=httpx2.Request("POST", "https://x")),
        _status_error(anthropic.RateLimitError, 429),
        _status_error(anthropic.AuthenticationError, 401),
        _status_error(anthropic.InternalServerError, 500),
    ],
)
def test_api_errors_become_llm_unavailable(error):
    gen, _ = generator(error)
    with pytest.raises(LLMUnavailable):
        gen.suggest(REQUEST)


def test_retry_message_includes_previous_attempt_and_problem():
    message = build_user_message(
        RegexRequest(
            instruction="find emails",
            columns=REQUEST.columns,
            previous=SUGGESTION,
            feedback="The pattern matched nothing.",
        )
    )
    assert "<previous_attempt>" in message
    assert r"\\S+@\\S+" in message
    assert "The pattern matched nothing." in message


def classifier(result):
    client = FakeClient(result)
    return ClaudeValueClassifier(
        model="claude-haiku-5-5", effort="low", timeout_seconds=5, client=client
    ), client


def test_classifier_limits_categories_and_sends_no_fallback():
    categories = ("Complaint", "Question", "Other")
    parsed = _batch_format(categories)(labels=[{"id": 0, "category": "Question"}])
    clf, client = classifier(response(parsed_output=parsed))

    batch = clf.classify(
        ClassifyBatchRequest(
            instruction="classify", categories=list(categories), values=["Can I pay later?"]
        )
    )

    assert batch.labels == [ValueLabel(id=0, category="Question")]
    call = client.calls[0]
    assert call["model"] == "claude-haiku-5-5"
    assert call["output_config"] == {"effort": "low"}
    # Claude Haiku 5.5 rejects server-side fallback, so none is requested.
    assert "fallbacks" not in call and "betas" not in call
    schema = call["output_format"].model_json_schema()
    assert schema["$defs"]["ValueLabel"]["properties"]["category"]["enum"] == list(categories)
    assert '0: "Can I pay later?"' in call["messages"][0]["content"]


def test_classifier_plan_uses_the_plan_schema():
    plan = ClassificationPlan(categories=["Positive", "Negative"], explanation="Sentiment.")
    clf, client = classifier(response(parsed_output=plan))

    assert (
        clf.plan(ClassifyPlanRequest(instruction="sentiment", column="Notes", samples=[])) == plan
    )
    assert client.calls[0]["output_format"] is ClassificationPlan


def test_extraction_uses_its_own_prompt_and_schema():
    extraction = ExtractSuggestion(
        pattern=r"@(?P<domain>\S+)", flags=[], column="Email", explanation="Domains."
    )
    gen, client = generator(response(parsed_output=extraction))

    assert gen.suggest_extraction(REQUEST) == extraction
    call = client.calls[0]
    assert call["output_format"] is ExtractSuggestion
    assert "named group" in call["system"]
    assert call["fallbacks"] == "default"  # Opus, like regex suggestions
