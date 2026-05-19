"""Resolve simplified attachment references to inline guided attachments."""

from __future__ import annotations

from app.config import Settings
from app.schemas.estimation_request import Attachment
from app.schemas.simplified_session import AttachmentProcessingStatus, AttachmentRef
from app.services.attachment_errors import AttachmentError
from app.services.document_extractor import DocumentTextExtractor, ExtractedAttachment


def process_attachment_refs(
    refs: list[AttachmentRef],
    settings: Settings,
) -> tuple[list[Attachment], list[ExtractedAttachment], list[AttachmentProcessingStatus]]:
    """Convert refs to guided attachments and extract text; per-file status on failure."""

    inline: list[Attachment] = []
    extracted: list[ExtractedAttachment] = []
    statuses: list[AttachmentProcessingStatus] = []
    extractor = DocumentTextExtractor(settings)

    for ref in refs:
        if ref.content_base64 is None:
            statuses.append(
                AttachmentProcessingStatus(
                    file_id=ref.file_id,
                    name=ref.name,
                    mime_type=ref.mime_type,
                    status="failed",
                    message="content_base64 is required until a dedicated upload API exists",
                )
            )
            continue

        attachment = Attachment(
            filename=ref.name,
            content_type=ref.mime_type,
            content_base64=ref.content_base64,
        )
        try:
            item = extractor.extract_one(attachment)
        except AttachmentError as exc:
            statuses.append(
                AttachmentProcessingStatus(
                    file_id=ref.file_id,
                    name=ref.name,
                    mime_type=ref.mime_type,
                    status="failed",
                    message=exc.message,
                )
            )
            continue

        inline.append(attachment)
        extracted.append(item)
        statuses.append(
            AttachmentProcessingStatus(
                file_id=ref.file_id,
                name=ref.name,
                mime_type=ref.mime_type,
                status="processed",
                message=None,
            )
        )

    return inline, extracted, statuses
