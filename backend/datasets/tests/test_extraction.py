"""
API tests for extraction with a fake LLM: new columns from named groups, the source
column choice, the self-correction loop, and applying over every row in batches.
"""

import pytest

from datasets.services import llm
from datasets.services.llm import ExtractSuggestion

pytestmark = pytest.mark.django_db

DOMAIN_PATTERN = r"@(?P<domain>[\w.-]+)"
NAME_PATTERN = r"(?P<first>\S+)\s+(?P<last>.+)"


def suggestion(pattern=DOMAIN_PATTERN, column="Email"):
    return ExtractSuggestion(
        pattern=pattern, flags=[], column=column, explanation="Extracts the parts."
    )


class FakeGenerator:
    """Returns queued extraction suggestions and records the requests it received."""

    def __init__(self, *suggestions):
        self.suggestions = list(suggestions)
        self.requests = []

    def suggest_extraction(self, request):
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
    return api_client.post("/api/datasets/", {"file": csv_file}, format="multipart").json()["id"]


def extract(api_client, dataset_id, instruction="Extract the email domain", **body):
    return api_client.post(
        f"/api/datasets/{dataset_id}/extractions/preview/",
        {"instruction": instruction, **body},
        format="json",
    )


def apply(api_client, transformation_id):
    return api_client.post(f"/api/transformations/{transformation_id}/apply/")


def rows(api_client, dataset_id):
    return api_client.get(f"/api/datasets/{dataset_id}/rows/").json()


def test_preview_extracts_named_groups_into_new_columns(api_client, dataset_id, fake_llm):
    fake_llm(suggestion())

    response = extract(api_client, dataset_id)

    assert response.status_code == 201
    transformation = response.json()["transformation"]
    assert transformation["kind"] == "extract"
    assert transformation["pattern"] == DOMAIN_PATTERN
    assert transformation["columns"] == ["Email"]
    assert transformation["params"] == {
        "source_column": "Email",
        "new_columns": [{"group": "domain", "column": "Email_domain"}],
    }
    assert transformation["stats"] == {
        "rows_matched": 3,
        "rows_scanned": 3,
        "total_rows": 3,
        "columns": {"Email_domain": 3},
    }
    assert response.json()["samples"][0] == {
        "row": 0,
        "value": "john.doe@example.com",
        "parts": {"Email_domain": "example.com"},
    }
    # Previewing changes nothing.
    assert rows(api_client, dataset_id)["columns"] == ["ID", "Name", "Email"]


def test_apply_inserts_the_columns_after_the_source(
    api_client, dataset_id, fake_llm, settings, monkeypatch
):
    settings.PREVIEW_ROW_LIMIT = 2
    # Small batches so the apply also exercises the batch-by-batch path.
    monkeypatch.setattr("datasets.services.file_io.ROWS_PER_BATCH", 2)
    fake_llm(suggestion(NAME_PATTERN, column="Name"))
    preview = extract(api_client, dataset_id, "Split Name into first and last name").json()
    assert preview["transformation"]["stats"]["rows_scanned"] == 2  # an estimate

    applied = apply(api_client, preview["transformation"]["id"]).json()

    assert applied["transformation"]["stats"]["rows_scanned"] == 3
    page = rows(api_client, dataset_id)
    assert page["columns"] == ["ID", "Name", "Name_first", "Name_last", "Email"]
    assert [row[2:4] for row in page["rows"]] == [
        ["John", "Doe"],
        ["Jane", "Smith"],
        ["Alice", "Brown"],
    ]
    # Only the new columns are highlighted.
    assert page["changed"] == [[row, col] for row in range(3) for col in (2, 3)]


def test_a_column_chosen_by_the_user_wins(api_client, dataset_id, fake_llm):
    fake_llm(suggestion(r"(?P<first>\w+)", column="Email"))

    params = extract(api_client, dataset_id, column="Name").json()["transformation"]["params"]

    assert params["source_column"] == "Name"
    assert params["new_columns"] == [{"group": "first", "column": "Name_first"}]


def test_pattern_without_named_groups_is_sent_back(api_client, dataset_id, fake_llm):
    generator = fake_llm(suggestion(r"@[\w.-]+"), suggestion())

    response = extract(api_client, dataset_id)

    assert response.status_code == 201
    assert "named group" in generator.requests[1].feedback
    assert generator.requests[1].previous.pattern == r"@[\w.-]+"


def test_unknown_llm_column_is_sent_back(api_client, dataset_id, fake_llm):
    generator = fake_llm(suggestion(column="E-mail"), suggestion())

    assert extract(api_client, dataset_id).status_code == 201
    assert "no column named 'E-mail'" in generator.requests[1].feedback


def test_matching_nothing_is_retried_then_returned(api_client, dataset_id, fake_llm):
    nothing = suggestion(r"(?P<zip>\d{5})")
    generator = fake_llm(nothing, nothing)

    response = extract(api_client, dataset_id)

    assert response.status_code == 201
    assert "matched nothing" in generator.requests[1].feedback
    assert response.json()["transformation"]["stats"]["rows_matched"] == 0


def test_gives_up_after_max_attempts(api_client, dataset_id, fake_llm):
    fake_llm(suggestion(r"(?P<x>"), suggestion(r"\d+"))

    response = extract(api_client, dataset_id)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "PATTERN_GENERATION_FAILED"


def test_unknown_user_column(api_client, dataset_id, fake_llm):
    fake_llm()

    response = extract(api_client, dataset_id, column="Nope")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "UNKNOWN_COLUMNS"


def test_new_column_names_do_not_clash(api_client, dataset_id, fake_llm):
    fake_llm(suggestion(), suggestion())
    apply(api_client, extract(api_client, dataset_id).json()["transformation"]["id"])

    params = extract(api_client, dataset_id).json()["transformation"]["params"]

    assert params["new_columns"] == [{"group": "domain", "column": "Email_domain_2"}]
