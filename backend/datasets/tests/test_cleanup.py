"""
Tests for data retention: uploads are not kept, and expired datasets are deleted with
their versions, transformations and files, along with leftover folders.
"""

import os
import time
from datetime import timedelta
from io import StringIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.utils import timezone

from datasets.models import Dataset, DatasetVersion, Transformation
from datasets.services import dataset_service

pytestmark = pytest.mark.django_db

CSV = b"ID,Email\n1,a@example.com\n2,b@example.com\n"


def upload(api_client) -> str:
    file = SimpleUploadedFile("people.csv", CSV, content_type="text/csv")
    return api_client.post("/api/datasets/", {"file": file}, format="multipart").json()["id"]


def stored_files(media_root, dataset_id) -> list[str]:
    folder = media_root / "datasets" / dataset_id
    return sorted(str(path.relative_to(folder)) for path in folder.rglob("*") if path.is_file())


def make_older(dataset_id, hours):
    Dataset.objects.filter(pk=dataset_id).update(created_at=timezone.now() - timedelta(hours=hours))


def test_upload_keeps_only_the_parsed_version(api_client, media_root):
    dataset_id = upload(api_client)

    assert stored_files(media_root, dataset_id) == ["versions/v1.parquet"]


def test_expired_datasets_are_deleted_with_their_files(api_client, media_root):
    old = upload(api_client)
    preview = api_client.post(
        f"/api/datasets/{old}/transformations/preview/",
        {"pattern": "@example", "replacement": "@test"},
        format="json",
    ).json()
    api_client.post(f"/api/transformations/{preview['transformation']['id']}/apply/")
    new = upload(api_client)
    make_older(old, hours=25)

    result = dataset_service.delete_expired_datasets(older_than=timedelta(hours=24))

    assert result == (1, 0)
    assert not Dataset.objects.filter(pk=old).exists()
    assert not DatasetVersion.objects.filter(dataset_id=old).exists()
    assert not Transformation.objects.filter(dataset_id=old).exists()
    assert not (media_root / "datasets" / old).exists()
    assert api_client.get(f"/api/datasets/{old}/").status_code == 404
    # Recent datasets are untouched.
    assert stored_files(media_root, new) == ["versions/v1.parquet"]


def test_leftover_folders_are_removed_only_once_old(media_root):
    day_ago = time.time() - 25 * 3600
    for name, modified in [("stale", day_ago), ("in-progress", time.time())]:
        folder = media_root / "datasets" / name / "versions"
        folder.mkdir(parents=True)
        (folder / "v1.parquet").write_bytes(b"data")
        os.utime(folder / "v1.parquet", (modified, modified))

    result = dataset_service.delete_expired_datasets(older_than=timedelta(hours=24))

    assert result == (0, 1)
    assert not (media_root / "datasets" / "stale").exists()
    # A folder without a dataset row may be an upload still being saved: keep it.
    assert (media_root / "datasets" / "in-progress").exists()


def test_command_reports_what_it_deleted(api_client):
    upload(api_client)
    out = StringIO()

    call_command("cleanup_datasets", "--hours", "0", stdout=out)

    assert out.getvalue().strip() == "Deleted 1 dataset(s) older than 0 h and 0 leftover folder(s)."
    assert not Dataset.objects.exists()
