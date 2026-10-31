"""
Domain errors raised by the service layer.

They are plain Python exceptions with no web-framework dependency; each carries a
stable `code` and the HTTP status it should map to. `exception_handler.py` turns them
into API responses.
"""

from http import HTTPStatus


class DomainError(Exception):
    code = "DOMAIN_ERROR"
    status_code = HTTPStatus.BAD_REQUEST
    default_message = "The request could not be processed."

    def __init__(self, message: str | None = None, details: dict | None = None):
        self.message = message or self.default_message
        self.details = details or {}
        super().__init__(self.message)


class UnsupportedFileType(DomainError):
    code = "UNSUPPORTED_FILE_TYPE"
    status_code = HTTPStatus.UNSUPPORTED_MEDIA_TYPE
    default_message = "Only .csv and .xlsx files are supported."


class FileTooLarge(DomainError):
    code = "FILE_TOO_LARGE"
    status_code = HTTPStatus.REQUEST_ENTITY_TOO_LARGE
    default_message = "The uploaded file exceeds the size limit."


class EmptyFile(DomainError):
    code = "EMPTY_FILE"
    default_message = "The uploaded file contains no data."


class FileParseError(DomainError):
    code = "FILE_PARSE_ERROR"
    default_message = "The uploaded file could not be parsed."


class InvalidRegex(DomainError):
    code = "INVALID_REGEX"
    default_message = "The regular expression is not valid."


class PatternMatchesEmpty(DomainError):
    code = "PATTERN_MATCHES_EMPTY"
    default_message = (
        "The pattern can match empty text, which would insert the replacement "
        "between every character. Make it match at least one character."
    )


class InvalidReplacement(DomainError):
    code = "INVALID_REPLACEMENT"
    default_message = (
        "The replacement value is not valid. Use \\1 or \\g<name> for group "
        "references and \\\\ for a literal backslash."
    )


class InvalidGroups(DomainError):
    code = "INVALID_GROUPS"
    default_message = (
        "The pattern needs at least one named group, such as (?P<domain>...), to become a column."
    )


class RegexTimeout(DomainError):
    code = "REGEX_TIMEOUT"
    status_code = HTTPStatus.UNPROCESSABLE_ENTITY
    default_message = "The pattern took too long to run. Try a simpler pattern."


class UnknownColumns(DomainError):
    code = "UNKNOWN_COLUMNS"
    default_message = "Some of the selected columns do not exist."


class NoTargetColumns(DomainError):
    code = "NO_TARGET_COLUMNS"
    default_message = "The dataset has no text columns. Select columns explicitly."


class TooManyValues(DomainError):
    code = "TOO_MANY_VALUES"
    status_code = HTTPStatus.UNPROCESSABLE_ENTITY
    default_message = "This column has too many distinct values to classify."


class NothingToClassify(DomainError):
    code = "NOTHING_TO_CLASSIFY"
    default_message = "This column has no values to classify."


class TooManyCategories(DomainError):
    code = "TOO_MANY_CATEGORIES"
    default_message = "Use at most 20 categories."


class TransformationConflict(DomainError):
    status_code = HTTPStatus.CONFLICT

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


class PatternGenerationFailed(DomainError):
    code = "PATTERN_GENERATION_FAILED"
    status_code = HTTPStatus.UNPROCESSABLE_ENTITY
    default_message = (
        "Could not turn the description into a working pattern. "
        "Try describing it differently or enter a regex manually."
    )


class LLMNotConfigured(DomainError):
    code = "LLM_NOT_CONFIGURED"
    status_code = HTTPStatus.SERVICE_UNAVAILABLE
    default_message = "The language model is not configured on the server."


class LLMUnavailable(DomainError):
    code = "LLM_UNAVAILABLE"
    status_code = HTTPStatus.SERVICE_UNAVAILABLE
    default_message = "The language model is temporarily unavailable. Please try again."


class LLMRefused(DomainError):
    code = "LLM_REFUSED"
    status_code = HTTPStatus.UNPROCESSABLE_ENTITY
    default_message = "The language model declined this request. Try rephrasing it."


class LLMBadOutput(DomainError):
    code = "LLM_BAD_OUTPUT"
    status_code = HTTPStatus.BAD_GATEWAY
    default_message = "The language model returned an unusable response. Please try again."
