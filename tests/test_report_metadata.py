import csv
import tempfile
import unittest
from pathlib import Path

from app.models import EmailAnalysisResult, FileQAReview, PIIMatch, PersonRecord, SourceExtractionMetadata
from app.reporting.csv_report import generate_csv_report
from app.reporting.file_review_csv import generate_file_review_csv
from app.reporting.html_report import generate_html_report
from app.runtime_metadata import (
    CSV_REPORT_SCHEMA_VERSION,
    CURRENT_BUILD_ID,
    FILE_REVIEW_SCHEMA_VERSION,
    HTML_REPORT_SCHEMA_VERSION,
)


def _sample_match() -> PIIMatch:
    return PIIMatch(
        pii_type="SSN",
        pii_category="government_identifier",
        pii_subtype="us_social_security_number",
        risk_level="HIGH",
        redacted_value="***-**-6789",
        excerpt="Employee SSN: ***-**-6789",
        source_ref="email_001.eml (email body)",
        char_offset=0,
        confidence=0.98,
        detection_method="regex",
        hipaa=False,
        ccpa=True,
        pipeda=False,
        notification_required=True,
        normalized_value="123456789",
        evidence=["ssn"],
    )


def _sample_phone_match() -> PIIMatch:
    return PIIMatch(
        pii_type="PHONE",
        pii_category="contact",
        pii_subtype="phone_number",
        risk_level="MEDIUM",
        redacted_value="(***) ***-0189",
        excerpt="Phone: (***) ***-0189",
        source_ref="email_002.eml (email body)",
        char_offset=0,
        confidence=0.88,
        detection_method="regex+context",
        hipaa=True,
        ccpa=True,
        pipeda=True,
        notification_required=False,
        normalized_value="2125550189",
        evidence=["phone"],
    )


class ReportMetadataTests(unittest.TestCase):
    def test_csv_report_includes_build_and_schema_columns(self) -> None:
        person = PersonRecord(
            person_id="person-1",
            canonical_email="amelia@example.com",
            canonical_name="Amelia Hughes",
            pii_matches=[_sample_match()],
            source_emails=["email_001.eml"],
            risk_score=88.2,
            highest_risk_level="HIGH",
            notification_required=True,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = generate_csv_report("job-123", [person], Path(temp_dir))
            with csv_path.open(newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                headers = reader.fieldnames or []
                row = next(reader)

        self.assertIn("Report Job ID", headers)
        self.assertIn("Report Schema Version", headers)
        self.assertIn("Report Build ID", headers)
        self.assertEqual(row["Report Job ID"], "job-123")
        self.assertEqual(row["Report Schema Version"], CSV_REPORT_SCHEMA_VERSION)
        self.assertEqual(row["Report Build ID"], CURRENT_BUILD_ID)

    def test_csv_report_emits_one_row_per_entity_source_file(self) -> None:
        person = PersonRecord(
            person_id="person-1",
            canonical_email="amelia@example.com",
            canonical_name="Amelia Hughes",
            pii_matches=[_sample_match(), _sample_phone_match()],
            source_emails=["email_001.eml", "email_002.eml"],
            risk_score=88.2,
            highest_risk_level="HIGH",
            notification_required=True,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = generate_csv_report("job-123", [person], Path(temp_dir))
            with csv_path.open(newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                rows = list(reader)

        self.assertEqual(2, len(rows))
        self.assertEqual(
            {"email_001.eml", "email_002.eml"},
            {row["Current Source Email File"] for row in rows},
        )

    def test_file_review_csv_includes_build_and_schema_columns(self) -> None:
        result = EmailAnalysisResult(
            eml_filename="email_001.eml",
            from_address="alerts@example.com",
            to_addresses=["amelia@example.com"],
            cc_addresses=[],
            bcc_addresses=[],
            subject="Coverage update",
            source_extractions={
                "email_001.eml > packet.xlsx": SourceExtractionMetadata(
                    source_ref="email_001.eml > packet.xlsx",
                    extraction_method="spreadsheet_rows",
                    parser="openpyxl",
                    table_count=1,
                    structured=True,
                )
            },
            qa_review=FileQAReview(
                reviewed=True,
                used_model=True,
                status="needs_review",
                needs_human_review=True,
                confidence=0.71,
                suspected_missing_types=["SSN"],
                reason="Potential unlabeled identifier in attachment.",
                model="qwen3:4b",
                followup_scanned=True,
                followup_match_count=2,
                followup_pii_types=["SSN", "DOB"],
                followup_source_refs=["email_001.eml > packet.xlsx"],
            ),
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = generate_file_review_csv("job-123", [result], Path(temp_dir))
            with csv_path.open(newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                headers = reader.fieldnames or []
                row = next(reader)

        self.assertIn("report_schema_version", headers)
        self.assertIn("report_build_id", headers)
        self.assertIn("qa_followup_match_count", headers)
        self.assertIn("structured_source_count", headers)
        self.assertEqual(row["report_schema_version"], FILE_REVIEW_SCHEMA_VERSION)
        self.assertEqual(row["report_build_id"], CURRENT_BUILD_ID)
        self.assertEqual(row["qa_followup_match_count"], "2")
        self.assertEqual(row["structured_source_count"], "1")

    def test_html_report_displays_build_and_schema_metadata(self) -> None:
        match = _sample_match()
        person = PersonRecord(
            person_id="person-1",
            canonical_email="amelia@example.com",
            canonical_name="Amelia Hughes",
            pii_matches=[match],
            source_emails=["email_001.eml"],
            attribution_methods=["content_block"],
            risk_score=88.2,
            highest_risk_level="HIGH",
            notification_required=True,
        )
        result = EmailAnalysisResult(
            eml_filename="email_001.eml",
            from_address="alerts@example.com",
            to_addresses=["amelia@example.com"],
            cc_addresses=[],
            bcc_addresses=[],
            subject="Coverage update",
            pii_matches=[match],
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            _, html = generate_html_report("job-123", [person], [result], Path(temp_dir))

        self.assertIn(CURRENT_BUILD_ID, html)
        self.assertIn(HTML_REPORT_SCHEMA_VERSION, html)
        self.assertIn(CSV_REPORT_SCHEMA_VERSION, html)
        self.assertIn(FILE_REVIEW_SCHEMA_VERSION, html)


if __name__ == "__main__":
    unittest.main()
