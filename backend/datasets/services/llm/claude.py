"""`RegexGenerator` backed by the Anthropic Claude API using structured outputs."""

import logging
import time

import anthropic
import pydantic

from datasets.exceptions import LLMBadOutput, LLMRefused, LLMUnavailable
from datasets.services.llm import prompts
from datasets.services.llm.base import RegexRequest, RegexSuggestion

logger = logging.getLogger(__name__)

# Server-side fallback: if a safety classifier declines the request, the API retries it
# on a model Anthropic recommends for that refusal category instead of failing.
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class ClaudeRegexGenerator:
    def __init__(
        self,
        *,
        model: str,
        effort: str,
        timeout_seconds: float,
        client: anthropic.Anthropic | None = None,
    ):
        self._model = model
        self._effort = effort
        # The SDK retries connection errors, 429 and 5xx responses on its own.
        self._client = client or anthropic.Anthropic(timeout=timeout_seconds, max_retries=2)

    def suggest(self, request: RegexRequest) -> RegexSuggestion:
        started = time.monotonic()
        try:
            response = self._client.beta.messages.parse(
                model=self._model,
                max_tokens=16000,
                betas=[FALLBACK_BETA],
                fallbacks="default",
                system=prompts.SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompts.build_user_message(request)}],
                output_config={"effort": self._effort},
                output_format=RegexSuggestion,
            )
        except anthropic.AuthenticationError:
            logger.error("Anthropic rejected the API key")
            raise LLMUnavailable("The language model credentials are invalid.") from None
        except anthropic.RateLimitError:
            raise LLMUnavailable("The language model is busy. Please try again shortly.") from None
        except anthropic.APITimeoutError:
            raise LLMUnavailable("The language model took too long to respond.") from None
        except anthropic.APIConnectionError:
            raise LLMUnavailable("Could not reach the language model.") from None
        except anthropic.APIStatusError as exc:
            logger.error("Anthropic API error %s: %s", exc.status_code, exc.message)
            raise LLMUnavailable() from None
        except pydantic.ValidationError as exc:
            raise LLMBadOutput(details={"reason": str(exc)}) from None

        logger.info(
            "LLM regex suggestion: model=%s stop=%s in=%s out=%s %.1fs request_id=%s",
            response.model,
            response.stop_reason,
            response.usage.input_tokens,
            response.usage.output_tokens,
            time.monotonic() - started,
            response._request_id,
        )

        if response.stop_reason == "refusal":
            raise LLMRefused()
        if response.stop_reason == "max_tokens" or response.parsed_output is None:
            raise LLMBadOutput()
        return response.parsed_output
