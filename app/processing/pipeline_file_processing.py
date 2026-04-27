"""Low-level file-processing helpers used by the top-level analysis pipeline."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from app.models import AttachmentProcessingRecord, EmailAnalysisResult, SourceExtractionMetadata
from app.processing.attachment_handler import extract_attachment_content
from app.processing.pii_engine import scan_text


logger = logging.getLogger(__name__)


def scan_source_text(
    result: EmailAnalysisResult,
    source_ref: str,
    text: str,
    metadata: SourceExtractionMetadata | None = None,
) -> None:
    """Store one extracted source and scan it for deterministic PII findings."""
    result.source_texts[source_ref] = text
    result.source_extractions[source_ref] = metadata or SourceExtractionMetadata(source_ref=source_ref)
    result.pii_matches.extend(scan_text(text, source_ref))


def process_attachment(result: EmailAnalysisResult, eml_filename: str, attachment) -> None:
    """Extract one attachment, attach extraction metadata, and scan its text."""
    try:
        record = AttachmentProcessingRecord(
            filename=attachment.filename,
            mime_type=attachment.mime_type,
        )
        result.attachments_processed.append(record)
        attachment_extraction = extract_attachment_content(attachment)
        record.extraction_method = attachment_extraction.extraction_method
        record.structured = attachment_extraction.structured
        record.page_count = attachment_extraction.page_count
        record.table_count = attachment_extraction.table_count
        record.ocr_used = attachment_extraction.ocr_used
        record.ocr_page_count = attachment_extraction.ocr_page_count
        record.ocr_avg_confidence = attachment_extraction.ocr_avg_confidence
        record.low_confidence_ocr = attachment_extraction.low_confidence_ocr
        record.warnings = list(attachment_extraction.warnings)

        source_ref = f"{eml_filename} > {attachment.filename}"
        attachment_scan_text = _build_attachment_scan_text(attachment.filename, attachment_extraction.text)
        scan_source_text(
            result,
            source_ref,
            attachment_scan_text,
            SourceExtractionMetadata(
                source_ref=source_ref,
                extraction_method=attachment_extraction.extraction_method or "attachment_text",
                parser=attachment_extraction.parser,
                page_count=attachment_extraction.page_count,
                table_count=attachment_extraction.table_count,
                structured=attachment_extraction.structured,
                ocr_used=attachment_extraction.ocr_used,
                ocr_page_count=attachment_extraction.ocr_page_count,
                ocr_avg_confidence=attachment_extraction.ocr_avg_confidence,
                low_confidence_ocr=attachment_extraction.low_confidence_ocr,
                warnings=list(attachment_extraction.warnings),
            ),
        )
    except Exception as exc:
        logger.warning("Error processing attachment %s: %s", attachment.filename, exc)


def error_result(file_path: Path, exc: Exception) -> EmailAnalysisResult:
    """Build a stable failure record for one `.eml` processing error."""
    return EmailAnalysisResult(
        eml_filename=file_path.name,
        from_address=None,
        from_name=None,
        to_addresses=[],
        to_names=[],
        cc_addresses=[],
        bcc_addresses=[],
        subject="",
        attachments_processed=[],
        error=str(exc),
    )


def append_result_json(results_file: Path, eml_result: EmailAnalysisResult) -> None:
    """Append one lightweight processing result record to the job's NDJSON log."""
    try:
        result_dict = {
            "eml_filename": eml_result.eml_filename,
            "from_address": eml_result.from_address,
            "to_addresses": eml_result.to_addresses,
            "cc_addresses": eml_result.cc_addresses,
            "bcc_addresses": eml_result.bcc_addresses,
            "subject": eml_result.subject,
            "pii_count": len(eml_result.pii_matches),
            "attachments_processed": [record.to_dict() for record in eml_result.attachments_processed],
            "attachment_count": len(eml_result.attachments_processed),
            "error": eml_result.error,
        }

        results_file.parent.mkdir(parents=True, exist_ok=True)
        with open(results_file, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(result_dict) + "\n")
    except Exception as exc:
        logger.warning("Failed to append result to %s: %s", results_file, exc)


def _build_attachment_scan_text(filename: str, attachment_text: str) -> str:
    """Compose the attachment filename banner plus extracted content for scanning."""
    attachment_scan_text = f"Attachment filename: {filename}\n"
    if attachment_text:
        attachment_scan_text += attachment_text
    return attachment_scan_text
