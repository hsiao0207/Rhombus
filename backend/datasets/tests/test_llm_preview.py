"""
API tests for natural-language previews with a fake LLM: user overrides, defaults and
the self-correction retry loop.
"""

import pytest

from datasets.services import llm
from datasets.services.llm import RegexSuggestion

pytestmark = pytest.mark.django_db

EMAIL_PATTERN = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,7}\b"
SPEC_INSTRUCTION = "Find email addresses in the Email column and replace them with 'REDACTED'."


def suggestion(pattern=EMAIL_PATTERN, replacement="REDACTED", columns=("Email",), flags=()):
    return RegexSuggestion(
        pattern=pattern,
        flags=list(flags),
        replacement=replacement,
        columns=list(columns),
        explanation="Matches email addresses.",
    )


class FakeGenerator:
    """Returns queued suggestions and records the requests it received."""

    def __init__(self, *suggestions):
        self.suggestions = list(suggestions)
        self.requests = []

    def suggest(self, request):
        self.requests.append(request)
        return self.suggestions.pop(0)


@pytest.fixture
def fake_llm(monkeypatch):
    def install(*suggestions):
        generator = FakeGenerator(*suggestions)
        monkeypatch.setattr(llm, "get_regex_generator", lambda: generator)
        return generator

    return install


@pytest.fixture
def dataset_id(api_client, csv_file):
    response = api_client.post("/api/datasets/", {"file": csv_file}, format="multipart")
    return response.json()["id"]


def preview(api_client, dataset_id, **body):
    return api_client.post(
        f"/api/datasets/{dataset_id}/transformations/preview/", body, format="json"
    )


def test_spec_example_end_to_end(api_client, dataset_id, fake_llm):
    generator = fake_llm(suggestion())

    response = preview(api_client, dataset_id, instruction=SPEC_INSTRUCTION)

    assert response.status_code == 201
    transformation = response.json()["transformation"]
    assert transformation["instruction"] == SPEC_INSTRUCTION
    assert transformation["explanation"] == "Matches email addresses."
    assert transformation["pattern"] == EMAIL_PATTERN
    assert transformation["replacement"] == "REDACTED"
    assert transformation["columns"] == ["Email"]
    assert transformation["stats"]["total_cells_changed"] == 3

    apply = api_client.post(f"/api/transformations/{transformation['id']}/apply/")
    assert apply.status_code == 200
    rows = api_client.get(f"/api/datasets/{dataset_id}/rows/").json()["rows"]
    assert [row[2] for row in rows] == ["REDACTED"] * 3

    # The LLM is grounded with column names, kinds and sample values.
    request = generator.requests[0]
    assert request.instruction == SPEC_INSTRUCTION
    email = next(c for c in request.columns if c.name == "Email")
    assert email.kind == "text"
    assert "john.doe@example.com" in email.samples


def test_explicit_replacement_and_columns_override_llm(api_client, dataset_id, fake_llm):
    fake_llm(suggestion(pattern="o", replacement="LLM", columns=["Email"]))

    body = preview(
        api_client, dataset_id, instruction="letter o", replacement="0", columns=["Name"]
    ).json()

    assert body["transformation"]["replacement"] == "0"
    assert body["transformation"]["columns"] == ["Name"]
    assert body["samples"][0] == {
        "row": 0,
        "column": "Name",
        "before": "John Doe",
        "after": "J0hn D0e",
    }


def test_blank_replacement_from_user_means_delete(api_client, dataset_id, fake_llm):
    fake_llm(suggestion(pattern=r"\s", replacement="LLM", columns=["Name"]))

    body = preview(api_client, dataset_id, instruction="spaces", replacement="").json()

    assert body["samples"][0]["after"] == "JohnDoe"


def test_unknown_llm_columns_fall_back_to_text_columns(api_client, dataset_id, fake_llm):
    fake_llm(suggestion(pattern="o", columns=["Nonexistent"]))

    body = preview(api_client, dataset_id, instruction="letter o").json()

    assert body["transformation"]["columns"] == ["Name", "Email"]


def test_missing_replacement_defaults_to_empty(api_client, dataset_id, fake_llm):
    fake_llm(suggestion(pattern="Doe", replacement=None, columns=["Name"]))

    body = preview(api_client, dataset_id, instruction="remove Doe").json()

    assert body["transformation"]["replacement"] == ""
    assert body["samples"][0]["after"] == "John "


def test_invalid_pattern_is_fed_back_for_self_correction(api_client, dataset_id, fake_llm):
    generator = fake_llm(suggestion(pattern="abc("), suggestion())

    response = preview(api_client, dataset_id, instruction=SPEC_INSTRUCTION)

    assert response.status_code == 201
    assert response.json()["transformation"]["pattern"] == EMAIL_PATTERN
    retry = generator.requests[1]
    assert retry.previous.pattern == "abc("
    assert "Invalid regular expression" in retry.feedback


def test_zero_matches_triggers_one_retry(api_client, dataset_id, fake_llm):
    generator = fake_llm(suggestion(pattern=r"\d{3}-\d{4}"), suggestion())

    body = preview(api_client, dataset_id, instruction=SPEC_INSTRUCTION).json()

    assert body["transformation"]["stats"]["total_matches"] == 3
    assert "matched nothing" in generator.requests[1].feedback


def test_no_op_replacement_triggers_one_retry(api_client, dataset_id, fake_llm):
    # Matches every email but "replaces" it with itself, so nothing would change.
    generator = fake_llm(suggestion(pattern=r"(\S+@\S+)", replacement=r"\1"), suggestion())

    body = preview(api_client, dataset_id, instruction=SPEC_INSTRUCTION).json()

    assert body["transformation"]["stats"]["total_cells_changed"] == 3
    assert "nothing would change" in generator.requests[1].feedback


def test_zero_matches_on_last_attempt_is_returned(api_client, dataset_id, fake_llm, settings):
    settings.LLM_MAX_ATTEMPTS = 1
    fake_llm(suggestion(pattern="zzz"))

    response = preview(api_client, dataset_id, instruction="find zzz")

    assert response.status_code == 201
    assert response.json()["transformation"]["stats"]["total_matches"] == 0


def test_gives_up_after_max_attempts(api_client, dataset_id, fake_llm):
    fake_llm(suggestion(pattern=r"\d*"), suggestion(pattern="abc("))

    response = preview(api_client, dataset_id, instruction="digits")

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "PATTERN_GENERATION_FAILED"
    assert error["details"]["pattern"] == "abc("
    assert error["details"]["attempts"] == 2


def test_user_column_errors_are_not_retried(api_client, dataset_id, fake_llm):
    generator = fake_llm(suggestion())

    response = preview(api_client, dataset_id, instruction="emails", columns=["Nope"])

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "UNKNOWN_COLUMNS"
    assert len(generator.requests) == 1


def test_pattern_takes_precedence_over_instruction(api_client, dataset_id, fake_llm):
    generator = fake_llm()

    body = preview(
        api_client, dataset_id, instruction="note to self", pattern="Doe", replacement="X"
    ).json()

    assert body["transformation"]["pattern"] == "Doe"
    assert body["transformation"]["instruction"] == "note to self"
    assert generator.requests == []


def test_requires_instruction_or_pattern(api_client, dataset_id):
    response = preview(api_client, dataset_id, instruction="", replacement="x")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_missing_api_key_returns_503(api_client, dataset_id, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    response = preview(api_client, dataset_id, instruction=SPEC_INSTRUCTION)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "LLM_NOT_CONFIGURED"
