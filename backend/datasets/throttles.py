"""Per-client rate limits for endpoints that cost money (LLM) or disk space (uploads)."""

from rest_framework.throttling import AnonRateThrottle


class PreviewThrottle(AnonRateThrottle):
    scope = "preview"


class ClassifyThrottle(AnonRateThrottle):
    scope = "classify"


class UploadThrottle(AnonRateThrottle):
    scope = "upload"
