from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from jinja2 import Template

from app.reporting.common import RISK_ORDER, build_report_metadata, humanize_pii
from app.runtime_metadata import (
    CSV_REPORT_SCHEMA_VERSION,
    FILE_REVIEW_SCHEMA_VERSION,
    HTML_REPORT_SCHEMA_VERSION,
)

logger = logging.getLogger(__name__)

TEMPLATE_PATH = Path(__file__).parent / "templates" / "report.html.j2"
BRAND_WORDMARK_PATH = Path(__file__).parent.parent / "static" / "brand" / "gezellig-dynamics-wordmark.svg"

CATEGORY_LABELS = {
    "government_identifier": "Government ID",
    "financial": "Financial",
    "health_identifier": "Health Identifier",
    "health_information": "Health Information",
    "professional_identifier": "Professional Identifier",
    "contact": "Contact",
    "personal_profile": "Profile",
    "identity": "Identity",
    "location": "Location",
    "vehicle_identifier": "Vehicle",
    "online_identifier": "Online Identifier",
}


def generate_html_report(job_id: str, persons: list, results: list, jobs_dir: Path) -> tuple[Path, str]:
    logger.info("Generating HTML report for job %s", job_id)

    report_metadata = build_report_metadata(HTML_REPORT_SCHEMA_VERSION)
    summary_context = _build_summary_context(persons, results)
    pii_type_matrix, pii_category_matrix = _collect_matrix_counts(persons)

    html_content = _render_template(
        job_id=job_id,
        timestamp=report_metadata["report_generated_utc"],
        build_label=report_metadata["report_build_label"],
        brand_wordmark_svg=_load_brand_wordmark_svg(),
        html_report_schema_version=HTML_REPORT_SCHEMA_VERSION,
        csv_report_schema_version=CSV_REPORT_SCHEMA_VERSION,
        file_review_schema_version=FILE_REVIEW_SCHEMA_VERSION,
        type_rows=_build_count_rows(pii_type_matrix, humanize_pii),
        category_rows=_build_count_rows(pii_category_matrix, _category_label),
        source_rows=_build_source_rows(results),
        person_rows=_build_person_rows(persons),
        **summary_context,
    )

    report_dir = Path(jobs_dir) / job_id / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_file = report_dir / "report.html"
    report_file.write_text(html_content, encoding="utf-8")

    logger.info("HTML report saved to %s", report_file)
    return report_file, html_content


def _build_summary_context(persons: list, results: list) -> dict[str, Any]:
    return {
        "total_files": len(results),
        "total_persons": len(persons),
        "total_high_critical": sum(
            1 for person in persons if person.highest_risk_level in ("CRITICAL", "HIGH")
        ),
        "total_medium": sum(1 for person in persons if person.highest_risk_level == "MEDIUM"),
        "total_low": sum(1 for person in persons if person.highest_risk_level == "LOW"),
        "total_notification": sum(1 for person in persons if person.notification_required),
        "total_attachments": sum(len(result.attachments_processed) for result in results),
        "emails_with_findings": sum(1 for result in results if result.pii_matches),
        "processing_errors": sum(1 for result in results if result.error),
        "hipaa_count": sum(1 for person in persons if person.regulations_triggered.get("HIPAA")),
        "ccpa_count": sum(1 for person in persons if person.regulations_triggered.get("CCPA")),
        "pipeda_count": sum(1 for person in persons if person.regulations_triggered.get("PIPEDA")),
        "files_ai_reviewed": sum(1 for result in results if result.qa_review and result.qa_review.reviewed),
        "files_human_review": sum(
            1 for result in results if result.qa_review and result.qa_review.needs_human_review
        ),
    }


def _collect_matrix_counts(persons: list) -> tuple[dict[str, int], dict[str, int]]:
    pii_type_matrix: dict[str, int] = {}
    pii_category_matrix: dict[str, int] = {}
    for person in persons:
        for match in person.pii_matches:
            pii_type_matrix[match.pii_type] = pii_type_matrix.get(match.pii_type, 0) + 1
            pii_category_matrix[match.pii_category] = pii_category_matrix.get(match.pii_category, 0) + 1
    return pii_type_matrix, pii_category_matrix


def _build_count_rows(counts: dict[str, int], label_resolver) -> list[dict[str, Any]]:
    return [
        {"label": label_resolver(code), "count": count}
        for code, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def _build_person_rows(persons: list) -> list[dict[str, Any]]:
    persons_sorted = sorted(
        persons,
        key=lambda person: (RISK_ORDER.get(person.highest_risk_level, 5), -person.risk_score),
    )
    return [_build_person_row(person) for person in persons_sorted]


def _build_person_row(person) -> dict[str, Any]:
    unique_types = sorted({match.pii_type for match in person.pii_matches})
    avg_confidence = (
        sum(match.confidence for match in person.pii_matches) / len(person.pii_matches)
        if person.pii_matches
        else 0.0
    )
    return {
        "person": person,
        "types": [{"code": pii_type, "label": humanize_pii(pii_type)} for pii_type in unique_types],
        "avg_confidence_pct": round(avg_confidence * 100),
        "attribution_confidence_pct": round(person.attribution_confidence * 100),
        "match_count": len(person.pii_matches),
        "findings": _build_finding_rows(person.pii_matches),
    }


def _build_finding_rows(matches: list) -> list[dict[str, Any]]:
    findings = sorted(
        matches,
        key=lambda match: (RISK_ORDER.get(match.risk_level, 5), -match.confidence, match.source_ref),
    )
    return [
        {
            "label": humanize_pii(match.pii_type),
            "type": match.pii_type,
            "subtype": match.pii_subtype.replace("_", " ").title(),
            "source_ref": match.source_ref,
            "confidence_pct": round(match.confidence * 100),
            "risk_level": match.risk_level,
            "redacted_value": match.redacted_value,
            "excerpt": match.excerpt,
            "evidence": ", ".join(match.evidence) if match.evidence else "pattern match",
        }
        for match in findings
    ]


def _build_source_rows(results: list) -> list[dict[str, Any]]:
    rows = []
    for result in sorted(results, key=lambda row: row.eml_filename):
        rows.append(
            {
                "eml_filename": result.eml_filename,
                "subject": result.subject or "(no subject)",
                "pii_count": len(result.pii_matches),
                "attachment_count": len(result.attachments_processed),
                "status": "Error" if result.error else ("Findings" if result.pii_matches else "Clear"),
                "error": result.error,
                "qa_status": result.qa_review.status if result.qa_review else "not_run",
                "qa_needs_human_review": bool(result.qa_review and result.qa_review.needs_human_review),
                "qa_reviewed": bool(result.qa_review and result.qa_review.reviewed),
                "qa_reason": result.qa_review.reason if result.qa_review else "",
                "qa_confidence_pct": round((result.qa_review.confidence if result.qa_review else 0.0) * 100),
            }
        )
    return rows


def _category_label(category: str) -> str:
    return CATEGORY_LABELS.get(category, category.replace("_", " ").title())


@lru_cache(maxsize=1)
def _load_template() -> Template:
    return Template(TEMPLATE_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _load_brand_wordmark_svg() -> str:
    return BRAND_WORDMARK_PATH.read_text(encoding="utf-8")


def _render_template(**context) -> str:
    return _load_template().render(**context)
