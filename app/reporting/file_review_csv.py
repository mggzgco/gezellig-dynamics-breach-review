import csv
import logging
from pathlib import Path

from app.reporting.common import build_report_metadata
from app.runtime_metadata import FILE_REVIEW_SCHEMA_VERSION

logger = logging.getLogger(__name__)


def generate_file_review_csv(job_id: str, results: list, jobs_dir: Path) -> Path:
    """Generate a file-level QA/export artifact for analyst review."""
    report_dir = Path(jobs_dir) / job_id / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_file = report_dir / "file_review.csv"

    fieldnames = [
        "report_job_id",
        "report_schema_version",
        "report_build_id",
        "report_generated_utc",
        "eml_filename",
        "subject",
        "finding_count",
        "attachment_count",
        "pii_types_found",
        "ocr_source_count",
        "low_confidence_ocr_source_count",
        "structured_source_count",
        "extraction_warning_count",
        "extraction_warning_refs",
        "qa_status",
        "qa_reviewed",
        "qa_used_model",
        "qa_confidence",
        "qa_needs_human_review",
        "qa_suspected_missing_types",
        "qa_questionable_detected_types",
        "qa_reason",
        "qa_evidence_quotes",
        "qa_model",
        "qa_error",
        "qa_followup_scanned",
        "qa_followup_match_count",
        "qa_followup_pii_types",
        "qa_followup_source_refs",
    ]

    with report_file.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        report_metadata = build_report_metadata(FILE_REVIEW_SCHEMA_VERSION)

        for result in sorted(results, key=lambda item: item.eml_filename):
            qa_review = result.qa_review
            pii_types = sorted({match.pii_type for match in result.pii_matches})
            source_extractions = list(result.source_extractions.items())
            ocr_source_refs = [source_ref for source_ref, metadata in source_extractions if metadata.ocr_used]
            low_confidence_refs = [
                source_ref for source_ref, metadata in source_extractions if metadata.low_confidence_ocr
            ]
            structured_source_refs = [
                source_ref for source_ref, metadata in source_extractions if metadata.structured
            ]
            warning_source_refs = [
                source_ref for source_ref, metadata in source_extractions if metadata.warnings
            ]
            writer.writerow(
                {
                    "report_job_id": job_id,
                    "report_schema_version": report_metadata["report_schema_version"],
                    "report_build_id": report_metadata["report_build_id"],
                    "report_generated_utc": report_metadata["report_generated_utc"],
                    "eml_filename": result.eml_filename,
                    "subject": result.subject or "",
                    "finding_count": len(result.pii_matches),
                    "attachment_count": len(result.attachments_processed),
                    "pii_types_found": ", ".join(pii_types),
                    "ocr_source_count": len(ocr_source_refs),
                    "low_confidence_ocr_source_count": len(low_confidence_refs),
                    "structured_source_count": len(structured_source_refs),
                    "extraction_warning_count": len(warning_source_refs),
                    "extraction_warning_refs": " | ".join(warning_source_refs),
                    "qa_status": qa_review.status if qa_review else "not_run",
                    "qa_reviewed": "Y" if qa_review and qa_review.reviewed else "N",
                    "qa_used_model": "Y" if qa_review and qa_review.used_model else "N",
                    "qa_confidence": f"{qa_review.confidence:.2f}" if qa_review else "0.00",
                    "qa_needs_human_review": "Y" if qa_review and qa_review.needs_human_review else "N",
                    "qa_suspected_missing_types": ", ".join(qa_review.suspected_missing_types) if qa_review else "",
                    "qa_questionable_detected_types": ", ".join(qa_review.questionable_detected_types) if qa_review else "",
                    "qa_reason": qa_review.reason if qa_review else "",
                    "qa_evidence_quotes": " | ".join(qa_review.evidence_quotes) if qa_review else "",
                    "qa_model": qa_review.model if qa_review else "",
                    "qa_error": qa_review.error if qa_review else "",
                    "qa_followup_scanned": "Y" if qa_review and qa_review.followup_scanned else "N",
                    "qa_followup_match_count": qa_review.followup_match_count if qa_review else 0,
                    "qa_followup_pii_types": ", ".join(qa_review.followup_pii_types) if qa_review else "",
                    "qa_followup_source_refs": " | ".join(qa_review.followup_source_refs) if qa_review else "",
                }
            )

    logger.info("File review CSV saved to %s", report_file)
    return report_file
