"""Shared fixtures: isolated media storage, a clean cache, an API client and sample files."""

import io

import pandas as pd
import pytest
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

SAMPLE_CSV = (
    "ID,Name,Email\n"
    "1,John Doe,john.doe@example.com\n"
    "2,Jane Smith,jane_smith@domain.com\n"
    "3,Alice Brown,alice.brown@website.org\n"
)


@pytest.fixture(autouse=True)
def media_root(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    return tmp_path


@pytest.fixture(autouse=True)
def clear_cache():
    # Throttle counters live in the cache; start every test with a clean slate.
    cache.clear()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def csv_file():
    return SimpleUploadedFile("people.csv", SAMPLE_CSV.encode(), content_type="text/csv")


@pytest.fixture
def xlsx_file():
    buffer = io.BytesIO()
    pd.read_csv(io.StringIO(SAMPLE_CSV)).to_excel(buffer, index=False)
    return SimpleUploadedFile(
        "people.xlsx",
        buffer.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
