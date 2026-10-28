import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from datasets.models import Dataset

pytestmark = pytest.mark.django_db

DATASETS_URL = "/api/datasets/"


def upload(api_client, file):
    return api_client.post(DATASETS_URL, {"file": file}, format="multipart")


@pytest.mark.parametrize("fixture_name,file_format", [("csv_file", "csv"), ("xlsx_file", "xlsx")])
def test_upload_creates_dataset_with_first_version(api_client, request, fixture_name, file_format):
    response = upload(api_client, request.getfixturevalue(fixture_name))

    assert response.status_code == 201
    body = response.json()
    assert body["file_format"] == file_format
    assert body["current_version"]["version_no"] == 1
    assert body["current_version"]["row_count"] == 3
    assert body["current_version"]["columns"] == [
        {"name": "ID", "kind": "numeric"},
        {"name": "Name", "kind": "text"},
        {"name": "Email", "kind": "text"},
    ]
    assert Dataset.objects.filter(pk=body["id"]).exists()


def test_upload_without_file_returns_validation_error(api_client):
    response = api_client.post(DATASETS_URL, {}, format="multipart")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "file" in response.json()["error"]["details"]["fields"]


def test_upload_unsupported_type(api_client):
    response = upload(api_client, SimpleUploadedFile("notes.txt", b"hello"))

    assert response.status_code == 415
    assert response.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"


def test_upload_header_only_csv_is_accepted_with_zero_rows(api_client):
    response = upload(api_client, SimpleUploadedFile("empty.csv", b"a,b\n"))

    assert response.status_code == 201
    assert response.json()["current_version"]["row_count"] == 0


def test_upload_blank_csv_is_rejected(api_client):
    response = upload(api_client, SimpleUploadedFile("blank.csv", b"\n\n"))

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "EMPTY_FILE"


def test_upload_too_large(api_client, settings, csv_file):
    settings.MAX_UPLOAD_SIZE_BYTES = 10

    response = upload(api_client, csv_file)

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "FILE_TOO_LARGE"
    assert not Dataset.objects.exists()


def test_corrupt_xlsx_returns_parse_error(api_client):
    response = upload(api_client, SimpleUploadedFile("broken.xlsx", b"not a zip file"))

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "FILE_PARSE_ERROR"


def test_retrieve_dataset(api_client, csv_file):
    dataset_id = upload(api_client, csv_file).json()["id"]

    response = api_client.get(f"{DATASETS_URL}{dataset_id}/")

    assert response.status_code == 200
    assert response.json()["original_name"] == "people.csv"


def test_retrieve_unknown_dataset_returns_404(api_client):
    response = api_client.get(f"{DATASETS_URL}00000000-0000-0000-0000-000000000000/")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_rows_are_paginated(api_client, csv_file):
    dataset_id = upload(api_client, csv_file).json()["id"]

    response = api_client.get(f"{DATASETS_URL}{dataset_id}/rows/", {"page": 2, "page_size": 2})

    assert response.status_code == 200
    assert response.json() == {
        "version": 1,
        "page": 2,
        "page_size": 2,
        "total_rows": 3,
        "total_pages": 2,
        "columns": ["ID", "Name", "Email"],
        "rows": [["3", "Alice Brown", "alice.brown@website.org"]],
        "changed": [],
    }


@pytest.mark.parametrize("params", [{"page": 0}, {"page_size": 10_000}, {"page": "abc"}])
def test_rows_rejects_invalid_paging(api_client, csv_file, params):
    dataset_id = upload(api_client, csv_file).json()["id"]

    response = api_client.get(f"{DATASETS_URL}{dataset_id}/rows/", params)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
