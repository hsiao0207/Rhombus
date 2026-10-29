"""
Unit tests for `ClaudeRegexGenerator` using a fake Anthropic client (no network calls):
request contents, refusal and unusable-output handling, and API error mapping.
"""

from types import SimpleNamespace

import anthropic
import httpx2
import pytest

from datasets.exceptions import LLMBadOutput, LLMRefused, LLMUnavailable
from datasets.services.llm import ColumnContext, RegexRequest, RegexSuggestion
from datasets.services.llm.claude import ClaudeRegexGenerator
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
