"""
DRF exception handler.

Translates domain errors and DRF's own exceptions into a single response shape:

    {"error": {"code": "FILE_PARSE_ERROR", "message": "...", "details": {...}}}

so the frontend only has to understand one error format.
"""

import logging

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from rest_framework import exceptions as drf_exceptions
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from datasets.exceptions import DomainError

logger = logging.getLogger(__name__)


def _error_response(code: str, message: str, details: dict, status_code: int) -> Response:
    return Response(
        {"error": {"code": code, "message": message, "details": details}},
        status=status_code,
    )


def api_exception_handler(exc, context):
    if isinstance(exc, DomainError):
        return _error_response(exc.code, exc.message, exc.details, exc.status_code)

    # Normalize Django's built-in exceptions to their DRF equivalents.
    if isinstance(exc, Http404):
        exc = drf_exceptions.NotFound()
    elif isinstance(exc, DjangoPermissionDenied):
        exc = drf_exceptions.PermissionDenied()

    response = drf_exception_handler(exc, context)
    if response is None:
        # Unhandled exception: log it and hide internals from the client.
        logger.exception("Unhandled error in %s", context.get("view"))
        return _error_response(
            "INTERNAL_ERROR",
            "An unexpected error occurred.",
            {},
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    if isinstance(exc, drf_exceptions.Throttled):
        minutes = max(1, round((exc.wait or 60) / 60))
        return _error_response(
            "THROTTLED",
            f"Too many requests. Please try again in about {minutes} minute(s).",
            {"retry_after_seconds": exc.wait},
            response.status_code,
        )

    if isinstance(exc, drf_exceptions.ValidationError):
        return _error_response(
            "VALIDATION_ERROR", "Invalid request.", {"fields": response.data}, response.status_code
        )

    code = getattr(exc, "default_code", "error").upper()
    message = str(getattr(exc, "detail", "Request failed."))
    return _error_response(code, message, {}, response.status_code)
