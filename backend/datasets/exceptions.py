"""
Domain errors and the API exception handler.

Services raise `DomainError` subclasses without knowing about HTTP. The handler below
translates both domain errors and DRF's own exceptions into a single response shape:

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

logger = logging.getLogger(__name__)


class DomainError(Exception):
    code = "DOMAIN_ERROR"
    status_code = status.HTTP_400_BAD_REQUEST
    default_message = "The request could not be processed."

    def __init__(self, message: str | None = None, details: dict | None = None):
        self.message = message or self.default_message
        self.details = details or {}
        super().__init__(self.message)


class UnsupportedFileType(DomainError):
    code = "UNSUPPORTED_FILE_TYPE"
    status_code = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    default_message = "Only .csv and .xlsx files are supported."


class FileTooLarge(DomainError):
    code = "FILE_TOO_LARGE"
    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    default_message = "The uploaded file exceeds the size limit."


class EmptyFile(DomainError):
    code = "EMPTY_FILE"
    default_message = "The uploaded file contains no data."


class FileParseError(DomainError):
    code = "FILE_PARSE_ERROR"
    default_message = "The uploaded file could not be parsed."


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

    if isinstance(exc, drf_exceptions.ValidationError):
        return _error_response(
            "VALIDATION_ERROR", "Invalid request.", {"fields": response.data}, response.status_code
        )

    code = getattr(exc, "default_code", "error").upper()
    message = str(getattr(exc, "detail", "Request failed."))
    return _error_response(code, message, {}, response.status_code)
