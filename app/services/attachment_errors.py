"""Domain errors for session attachment handling."""

from __future__ import annotations


class AttachmentError(Exception):
    """Base attachment processing error with HTTP mapping metadata."""

    def __init__(self, *, code: str, message: str, status_code: int) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class UnsupportedMimeTypeError(AttachmentError):
    def __init__(self, mime: str) -> None:
        super().__init__(
            code="UNSUPPORTED_MIME_TYPE",
            message=f"Unsupported attachment MIME type: {mime}",
            status_code=422,
        )


class AttachmentTooLargeError(AttachmentError):
    def __init__(self, *, filename: str, size_bytes: int, limit_bytes: int) -> None:
        super().__init__(
            code="ATTACHMENT_TOO_LARGE",
            message=(
                f"Attachment «{filename}» exceeds {limit_bytes} bytes "
                f"(decoded size {size_bytes})."
            ),
            status_code=413,
        )


class UnsupportedFormatError(AttachmentError):
    def __init__(self, *, filename: str, hint: str) -> None:
        super().__init__(
            code="UNSUPPORTED_FORMAT",
            message=f"Attachment «{filename}»: {hint}",
            status_code=422,
        )


class ExtractionFailedError(AttachmentError):
    def __init__(self, *, filename: str, reason: str) -> None:
        super().__init__(
            code="EXTRACTION_FAILED",
            message=f"Could not extract text from «{filename}»: {reason}",
            status_code=422,
        )
