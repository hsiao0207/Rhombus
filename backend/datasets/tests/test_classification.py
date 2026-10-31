"""
API tests for LLM classification with a fake classifier: one LLM label per distinct
value, batching and retries, limits, and applying the mapping stored at preview time.
"""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from datasets.services import llm
from datasets.services.llm import ClassificationBatch, ClassificationPlan, ValueLabel

pytestmark = pytest.mark.django_db

NOTES_CSV = (
    "ID,Notes,Status,Blank\n"
    "1,My order hasn't arrived,open,\n"
    "2,Can I change my address?,open,\n"
    "3,Package came damaged,closed,\n"
    "4,Can I change my address?,open,\n"
    "5,,closed,\n"
)
INSTRUCTION = "Classify as Complaint or Question"


def by_question_mark(value: str) -> str:
    return "Question" if "?" in value else "Complaint"


class FakeClassifier:
    """Labels values with `label_for` and records every request it receives."""

    def __init__(self, categories=("Complaint", "Question"), label_for=by_question_mark):
        self.categories = list(categories)
        self.label_for = label_for
        self.plan_requests = []
        self.batch_requests = []

    def plan(self, request):
        self.plan_requests.append(request)
        return ClassificationPlan(categories=self.categories, explanation="Sorts the notes.")

    def classify(self, request):
        self.batch_requests.append(request)
        return ClassificationBatch(
            labels=[
                ValueLabel(id=index, category=self.label_for(value))
                for index, value in enumerate(request.values)
            ]
        )


@pytest.fixture
def fake_classifier(monkeypatch):
    classifier = FakeClassifier()
    monkeypatch.setattr(llm, "get_value_classifier", lambda: classifier)
    return classifier


@pytest.fixture
def dataset_id(api_client):
    upload = SimpleUploadedFile("notes.csv", NOTES_CSV.encode(), content_type="text/csv")
    return api_client.post("/api/datasets/", {"file": upload}, format="multipart").json()["id"]


def classify(api_client, dataset_id, column="Notes", instruction=INSTRUCTION):
    return api_client.post(
        f"/api/datasets/{dataset_id}/classifications/preview/",
        {"column": column, "instruction": instruction},
        format="json",
    )


def apply(api_client, transformation_id):
    return api_client.post(f"/api/transformations/{transformation_id}/apply/")


def rows(api_client, dataset_id):
    return api_client.get(f"/api/datasets/{dataset_id}/rows/").json()


def test_preview_classifies_each_distinct_value_once(api_client, dataset_id, fake_classifier):
    response = classify(api_client, dataset_id)

    assert response.status_code == 201
    transformation = response.json()["transformation"]
    assert transformation["kind"] == "classify"
    assert transformation["status"] == "previewed"
    assert transformation["explanation"] == "Sorts the notes."
    # The mapping stays on the server.
    assert transformation["params"] == {
        "source_column": "Notes",
        "new_column": "Notes_category",
        "categories": ["Complaint", "Question", "Other"],
    }
    assert transformation["stats"] == {
        "categories": {"Complaint": 2, "Question": 2, "Other": 0},
        "distinct_values": 3,
        "rows_classified": 4,
        "total_rows": 5,
    }
    # Three distinct values in one batch; the repeated value and the empty cell are not sent.
    [batch] = fake_classifier.batch_requests
    assert sorted(batch.values) == [
        "Can I change my address?",
        "My order hasn't arrived",
        "Package came damaged",
    ]
    assert batch.categories == ["Complaint", "Question", "Other"]
    assert response.json()["samples"][0] == {
        "row": 0,
        "column": "Notes",
        "before": "My order hasn't arrived",
        "after": "Complaint",
    }
    # Previewing changes nothing.
    assert rows(api_client, dataset_id)["columns"] == ["ID", "Notes", "Status", "Blank"]


def test_apply_adds_the_column_from_the_stored_mapping(api_client, dataset_id, fake_classifier):
    transformation_id = classify(api_client, dataset_id).json()["transformation"]["id"]
    calls_before_apply = len(fake_classifier.batch_requests)
    # If apply asked the LLM again, every value would now come back as "Other".
    fake_classifier.label_for = lambda value: "Other"

    response = apply(api_client, transformation_id)

    assert response.status_code == 200
    assert response.json()["transformation"]["result_version"] == 2
    assert len(fake_classifier.batch_requests) == calls_before_apply
    page = rows(api_client, dataset_id)
    assert page["columns"] == ["ID", "Notes", "Notes_category", "Status", "Blank"]
    assert [row[2] for row in page["rows"]] == [
        "Complaint",
        "Question",
        "Complaint",
        "Question",
        None,  # empty notes stay empty
    ]
    # The whole new column is highlighted; the original columns are unchanged.
    assert page["changed"] == [[row, 2] for row in range(5)]


def test_values_are_sent_in_batches(api_client, dataset_id, fake_classifier, settings):
    settings.CLASSIFY_BATCH_SIZE = 2

    classify(api_client, dataset_id)

    assert sorted(len(batch.values) for batch in fake_classifier.batch_requests) == [1, 2]


def test_skipped_or_mislabeled_values_get_one_retry(api_client, dataset_id, fake_classifier):
    answers = {"Package came damaged": ["Bogus", "Complaint"]}  # wrong first, right on retry

    def label_for(value):
        return answers[value].pop(0) if value in answers else by_question_mark(value)

    fake_classifier.label_for = label_for

    stats = classify(api_client, dataset_id).json()["transformation"]["stats"]

    assert len(fake_classifier.batch_requests) == 2
    assert fake_classifier.batch_requests[1].values == ["Package came damaged"]
    assert stats["categories"] == {"Complaint": 2, "Question": 2, "Other": 0}


def test_values_still_unlabeled_after_the_retry_are_marked(api_client, dataset_id, fake_classifier):
    fake_classifier.label_for = lambda value: "Bogus" if "damaged" in value else "Question"

    stats = classify(api_client, dataset_id).json()["transformation"]["stats"]

    assert stats["categories"]["Unclassified"] == 1


def test_llm_categories_are_cleaned_up(api_client, dataset_id, fake_classifier):
    fake_classifier.categories = [" Complaint ", "other", "complaint", "", "Question"]

    params = classify(api_client, dataset_id).json()["transformation"]["params"]

    assert params["categories"] == ["Complaint", "Question", "Other"]


def test_too_many_categories(api_client, dataset_id, fake_classifier, settings):
    settings.MAX_CLASSIFY_CATEGORIES = 1

    response = classify(api_client, dataset_id)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "TOO_MANY_CATEGORIES"


def test_too_many_distinct_values(api_client, dataset_id, fake_classifier, settings):
    settings.MAX_CLASSIFY_VALUES = 2

    response = classify(api_client, dataset_id)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "TOO_MANY_VALUES"
    assert fake_classifier.plan_requests == []  # rejected before any LLM call


def test_unknown_column(api_client, dataset_id, fake_classifier):
    response = classify(api_client, dataset_id, column="Nope")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "UNKNOWN_COLUMNS"


def test_empty_column(api_client, dataset_id, fake_classifier):
    response = classify(api_client, dataset_id, column="Blank")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "NOTHING_TO_CLASSIFY"


def test_new_column_name_does_not_clash(api_client, dataset_id, fake_classifier):
    first = classify(api_client, dataset_id).json()["transformation"]["id"]
    apply(api_client, first)

    params = classify(api_client, dataset_id).json()["transformation"]["params"]

    assert params["new_column"] == "Notes_category_2"


def test_missing_api_key_returns_503(api_client, dataset_id, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    response = classify(api_client, dataset_id)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "LLM_NOT_CONFIGURED"
