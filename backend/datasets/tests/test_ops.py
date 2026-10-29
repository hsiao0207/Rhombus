"""Tests for operational safeguards: the health check and upload rate limiting."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from datasets.throttles import UploadThrottle

pytestmark = pytest.mark.django_db


def test_health(api_client):
    response = api_client.get("/api/health/")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_uploads_are_rate_limited(api_client, monkeypatch):
    monkeypatch.setattr(UploadThrottle, "THROTTLE_RATES", {"upload": "2/hour"})

    def upload():
        file = SimpleUploadedFile("a.csv", b"a\n1\n")
        return api_client.post("/api/datasets/", {"file": file}, format="multipart")

    assert upload().status_code == 201
    assert upload().status_code == 201
    response = upload()

    assert response.status_code == 429
    error = response.json()["error"]
    assert error["code"] == "THROTTLED"
    assert error["details"]["retry_after_seconds"] > 0
