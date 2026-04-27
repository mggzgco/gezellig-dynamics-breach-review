import csv
import logging
from pathlib import Path

from app.reporting.common import build_report_metadata, source_email_file
from app.runtime_metadata import CSV_REPORT_SCHEMA_VERSION

logger = logging.getLogger(__name__)

# Human-readable header mapping
HEADER_MAPPING = {
    "report_job_id": "Report Job ID",
    "report_schema_version": "Report Schema Version",
    "report_build_id": "Report Build ID",
    "report_generated_utc": "Report Generated UTC",
    "person_id": "Person ID",
    "canonical_name": "Name",
    "canonical_email": "Email Address",
    "entity_type": "Entity Type",
    "risk_band": "Risk Level",
    "risk_score": "Risk Score",
    "attribution_confidence": "Attribution Confidence",
    "attribution_methods": "Attribution Methods",
    "entity_source_file_count": "Entity Source File Count",
    "entity_source_files": "Entity Source Email Files",
    "current_source_file": "Current Source Email File",
    "current_source_ref_count": "Current Source Reference Count",
    "current_source_refs": "Current Source References",
    "pii_match_count": "PII Matches",
    "unique_pii_type_count": "Unique PII Types",
    "pii_types_found": "PII Types Found",
    "avg_confidence": "Average Confidence",
    "hipaa_triggered": "HIPAA Triggered",
    "ccpa_triggered": "CCPA Triggered",
    "pipeda_triggered": "PIPEDA Triggered",
    "notification_required": "Notification Required",
    "source_file_count": "# Source Files",
    "source_files": "Source Email Files",
    # PII Type mappings (convert underscores to spaces, proper case)
    "SSN": "Social Security Number",
    "SIN": "Canadian Social Insurance #",
    "CREDIT_CARD": "Credit Card",
    "BANK_ACCOUNT": "Bank Account",
    "PASSPORT": "Passport",
    "DRIVERS_LICENSE": "Driver's License",
    "MEDICARE": "Medicare Beneficiary ID",
    "MRN": "Medical Record Number",
    "NPI": "National Provider ID",
    "EMAIL": "Email Address (Content)",
    "PHONE": "Phone Number",
    "DOB": "Date of Birth",
    "ADDRESS": "Physical Address",
    "ZIP": "ZIP/Postal Code",
    "VIN": "Vehicle ID Number",
    "IBAN": "IBAN",
    "ICD10": "ICD-10 Code",
    "NDC": "NDC Drug Code",
    "FULL_NAME": "Full Name",
    "IPV4": "IP Address",
    "EIN": "Employer ID Number",
}


def _get_human_readable_header(field_name: str) -> str:
    """Convert technical field name to human-readable header."""
    if field_name in HEADER_MAPPING:
        return HEADER_MAPPING[field_name]
    # Fallback: convert snake_case to Title Case
    return " ".join(word.title() for word in field_name.split("_"))


def generate_csv_report(job_id: str, persons: list, jobs_dir: Path) -> Path:
    """
    Generate CSV report from analysis results.
    One row per entity per source email file so file-level findings do not
    inherit the union of all matches seen for that entity across the corpus.
    Returns path to generated CSV file with human-readable headers.
    """
    logger.info(f"Generating CSV report for job {job_id}")

    # Get all PII types found across all persons
    all_pii_types = set()
    for person in persons:
        for match in person.pii_matches:
            all_pii_types.add(match.pii_type)

    all_pii_types = sorted(all_pii_types)

    # CSV columns (internal field names)
    fieldnames = [
        "report_job_id",
        "report_schema_version",
        "report_build_id",
        "report_generated_utc",
        "person_id",
        "canonical_name",
        "canonical_email",
        "entity_type",
        "risk_band",
        "risk_score",
        "attribution_confidence",
        "attribution_methods",
        "entity_source_file_count",
        "entity_source_files",
        "current_source_file",
        "current_source_ref_count",
        "current_source_refs",
        "pii_match_count",
        "unique_pii_type_count",
        "pii_types_found",
        "avg_confidence",
    ]
    fieldnames.extend(all_pii_types)
    fieldnames.extend([
        "hipaa_triggered",
        "ccpa_triggered",
        "pipeda_triggered",
        "notification_required",
        "source_file_count",
        "source_files",
    ])

    # Create human-readable headers
    human_readable_headers = [_get_human_readable_header(field) for field in fieldnames]

    # Build report directory
    report_dir = Path(jobs_dir) / job_id / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_file = report_dir / "report.csv"
    report_metadata = build_report_metadata(CSV_REPORT_SCHEMA_VERSION)

    # Write CSV
    with open(report_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)

        # Write custom header row with human-readable names
        f.write(",".join(f'"{header}"' if "," in header else header for header in human_readable_headers) + "\n")

        for person in persons:
            matches_by_file: dict[str, list] = {}
            for match in person.pii_matches:
                matches_by_file.setdefault(source_email_file(match.source_ref), []).append(match)

            for current_source_file, source_matches in sorted(matches_by_file.items()):
                pii_found = {pii_type: "N" for pii_type in all_pii_types}
                for match in source_matches:
                    pii_found[match.pii_type] = "Y"

                unique_types = sorted({match.pii_type for match in source_matches})
                avg_confidence = (
                    sum(getattr(match, "confidence", 1.0) for match in source_matches) / len(source_matches)
                    if source_matches else 0.0
                )
                risk_band = max(
                    (match.risk_level for match in source_matches),
                    key=lambda value: {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "NONE": 0}.get(value, 0),
                    default=person.highest_risk_level,
                )
                source_refs = sorted({match.source_ref for match in source_matches})

                row = {
                    "report_job_id": job_id,
                    "report_schema_version": report_metadata["report_schema_version"],
                    "report_build_id": report_metadata["report_build_id"],
                    "report_generated_utc": report_metadata["report_generated_utc"],
                    "person_id": person.person_id,
                    "canonical_name": person.canonical_name or "",
                    "canonical_email": person.canonical_email or "",
                    "entity_type": person.entity_type,
                    "risk_band": risk_band,
                    "risk_score": f"{person.risk_score:.2f}",
                    "attribution_confidence": f"{person.attribution_confidence:.2f}",
                    "attribution_methods": ", ".join(person.attribution_methods),
                    "entity_source_file_count": len(person.source_emails),
                    "entity_source_files": "|".join(sorted(person.source_emails)),
                    "current_source_file": current_source_file,
                    "current_source_ref_count": len(source_refs),
                    "current_source_refs": "|".join(source_refs),
                    "pii_match_count": len(source_matches),
                    "unique_pii_type_count": len(unique_types),
                    "pii_types_found": ", ".join(unique_types),
                    "avg_confidence": f"{avg_confidence:.2f}",
                }

                row.update(pii_found)
                row.update({
                    "hipaa_triggered": "Y" if any(match.hipaa for match in source_matches) else "N",
                    "ccpa_triggered": "Y" if any(match.ccpa for match in source_matches) else "N",
                    "pipeda_triggered": "Y" if any(match.pipeda for match in source_matches) else "N",
                    "notification_required": "Y" if any(match.notification_required for match in source_matches) else "N",
                    "source_file_count": 1,
                    "source_files": current_source_file,
                })

                writer.writerow(row)

    logger.info(f"CSV report saved to {report_file}")
    return report_file
