"""
API tests for the preview/apply flow with explicit regexes: versioning, change
highlighting, chaining and conflict detection.
"""

import pytest

from datasets.models import Transformation

pytestmark = pytest.mark.django_db

EMAIL_PATTERN = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,7}\b"


@pytest.fixture
def dataset_id(api_client, csv_file):
    response = api_client.post("/api/datasets/", {"file": csv_file}, format="multipart")
    return response.json()["id"]


def preview(api_client, dataset_id, **body):
    return api_client.post(
        f"/api/datasets/{dataset_id}/transformations/preview/", body, format="json"
    )


def apply(api_client, transformation_id):
    return api_client.post(f"/api/transformations/{transformation_id}/apply/")


def rows(api_client, dataset_id):
    return api_client.get(f"/api/datasets/{dataset_id}/rows/").json()


def test_preview_reports_changes_without_modifying_data(api_client, dataset_id):
    response = preview(
        api_client, dataset_id, pattern=EMAIL_PATTERN, replacement="REDACTED", columns=["Email"]
    )

    assert response.status_code == 201
    body = response.json()
    assert body["transformation"]["status"] == "previewed"
    assert body["transformation"]["source_version"] == 1
    assert body["transformation"]["result_version"] is None
    assert body["transformation"]["stats"]["total_cells_changed"] == 3
    assert body["samples"][0] == {
        "row": 0,
        "column": "Email",
        "before": "john.doe@example.com",
        "after": "REDACTED",
    }
    assert rows(api_client, dataset_id)["rows"][0][2] == "john.doe@example.com"


def test_apply_creates_new_version_and_highlights_changes(api_client, dataset_id):
    transformation_id = preview(
        api_client, dataset_id, pattern=EMAIL_PATTERN, replacement="REDACTED", columns=["Email"]
    ).json()["transformation"]["id"]

    response = apply(api_client, transformation_id)

    assert response.status_code == 200
    body = response.json()
    assert body["transformation"]["status"] == "applied"
    assert body["transformation"]["result_version"] == 2
    assert body["dataset"]["current_version"]["version_no"] == 2

    page = rows(api_client, dataset_id)
    assert page["version"] == 2
    assert [row[2] for row in page["rows"]] == ["REDACTED"] * 3
    assert page["changed"] == [[0, 2], [1, 2], [2, 2]]


def test_preview_scans_only_the_first_rows_but_apply_covers_all(
    api_client, dataset_id, settings, monkeypatch
):
    settings.PREVIEW_ROW_LIMIT = 2
    # Small batches so the apply also exercises the batch-by-batch path.
    monkeypatch.setattr("datasets.services.file_io.ROWS_PER_BATCH", 2)

    response = preview(
        api_client, dataset_id, pattern=EMAIL_PATTERN, replacement="REDACTED", columns=["Email"]
    )

    stats = response.json()["transformation"]["stats"]
    assert stats["rows_scanned"] == 2
    assert stats["total_rows"] == 3
    assert stats["total_cells_changed"] == 2  # an estimate from the scanned rows

    applied = apply(api_client, response.json()["transformation"]["id"]).json()
    assert applied["transformation"]["stats"]["rows_scanned"] == 3
    assert applied["transformation"]["stats"]["total_cells_changed"] == 3
    assert [row[2] for row in rows(api_client, dataset_id)["rows"]] == ["REDACTED"] * 3


def test_default_columns_are_text_columns_only(api_client, dataset_id):
    body = preview(api_client, dataset_id, pattern=r"\d", replacement="#").json()

    # "ID" is numeric, so only Name and Email are targeted.
    assert body["transformation"]["columns"] == ["Name", "Email"]


def test_transformations_can_be_chained(api_client, dataset_id):
    first = preview(api_client, dataset_id, pattern="Doe", replacement="D.").json()
    apply(api_client, first["transformation"]["id"])
    second = preview(api_client, dataset_id, pattern="John", replacement="J.").json()

    assert second["transformation"]["source_version"] == 2
    apply(api_client, second["transformation"]["id"])
    assert rows(api_client, dataset_id)["rows"][0][1] == "J. D."


def test_applying_twice_is_rejected(api_client, dataset_id):
    transformation_id = preview(api_client, dataset_id, pattern="Doe", replacement="X").json()[
        "transformation"
    ]["id"]
    apply(api_client, transformation_id)

    response = apply(api_client, transformation_id)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ALREADY_APPLIED"


def test_stale_preview_is_rejected(api_client, dataset_id):
    old = preview(api_client, dataset_id, pattern="Doe", replacement="X").json()
    new = preview(api_client, dataset_id, pattern="Smith", replacement="Y").json()
    apply(api_client, new["transformation"]["id"])

    response = apply(api_client, old["transformation"]["id"])

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "STALE_VERSION"
    assert Transformation.objects.get(pk=old["transformation"]["id"]).status == "previewed"


@pytest.mark.parametrize(
    "body,status_code,code",
    [
        ({"pattern": "abc("}, 400, "INVALID_REGEX"),
        ({"pattern": r"\d*"}, 400, "PATTERN_MATCHES_EMPTY"),
        ({"pattern": "a", "columns": ["Nope"]}, 400, "UNKNOWN_COLUMNS"),
        ({"pattern": "a", "flags": ["VERBOSE"]}, 400, "VALIDATION_ERROR"),
        ({"replacement": "x"}, 400, "VALIDATION_ERROR"),
    ],
)
def test_preview_validation_errors(api_client, dataset_id, body, status_code, code):
    response = preview(api_client, dataset_id, **body)

    assert response.status_code == status_code
    assert response.json()["error"]["code"] == code


def test_preview_unknown_dataset_returns_404(api_client):
    response = preview(api_client, "00000000-0000-0000-0000-000000000000", pattern="a")
    assert response.status_code == 404


def test_apply_unknown_transformation_returns_404(api_client):
    response = apply(api_client, "00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
