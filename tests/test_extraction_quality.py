import io
import unittest
from pathlib import Path
from unittest.mock import patch

import openpyxl

from app.models import Attachment, EmailAnalysisResult, SourceExtractionMetadata
from app.processing.attachment_handler import extract_attachment_content
from app.processing.extractors.ocr_layout import _parse_tsv_output, extract_tsv_text
from app.processing.extractors.ocr_normalization import normalize_ocr_lines
from app.processing.extractors.pdf_extractor import extract_with_metadata as extract_pdf_with_metadata
from app.processing.extractors.types import ExtractedText
from app.processing.local_llm_file_qa import LocalLLMFileQAHelper
from app.pii_validation import mrn_check


class ExtractionQualityTests(unittest.TestCase):
    def test_tesseract_tsv_parser_preserves_line_order_and_confidence(self) -> None:
        raw_tsv = "\n".join(
            [
                "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext",
                "5\t1\t1\t1\t1\t1\t10\t10\t30\t10\t95.5\tFull",
                "5\t1\t1\t1\t1\t2\t50\t10\t30\t10\t94.1\tName:",
                "5\t1\t1\t1\t1\t3\t120\t10\t60\t10\t93.2\tAlice",
                "5\t1\t1\t1\t1\t4\t190\t10\t60\t10\t92.4\tNguyen",
                "5\t1\t1\t1\t2\t1\t10\t30\t20\t10\t91.0\tDOB:",
                "5\t1\t1\t1\t2\t2\t60\t30\t80\t10\t90.0\t02/14/1986",
            ]
        )

        extraction = _parse_tsv_output(raw_tsv, prefix="[OCR]")

        self.assertIn("Full Name: Alice Nguyen", extraction.text)
        self.assertIn("DOB: 02/14/1986", extraction.text)
        self.assertTrue(extraction.ocr_used)
        self.assertFalse(extraction.low_confidence_ocr)
        self.assertGreater(extraction.ocr_avg_confidence, 90)

    def test_ocr_normalization_repairs_common_scanned_record_damage(self) -> None:
        normalized, warnings = normalize_ocr_lines(
            [
                "Full Name-CalebChen",
                "Full Name: Em ma Walker",
                "Date of ith O8/22/I848",
                "ssh: 97I-96-8593",
                "Home Adress 4473 Riverview Avenus, Charlotte, NC28203",
                "Personal Ema danielsingh @yahoocom",
                "DiagnesisCode: £119",
                "Diagnosis Code: 110",
                "Nbe:00597-0087-17",
                "IBAN: FR14 2004 1010 0505 0001 302 606",
                "Medicare Number: 5VX4TWEMK87",
                "Personal Email: calebchen2@protonmail Lcom",
                "Personal Email: jack.foster6 @g mai Lcom",
                "Personal Email: amelia.hughes$ @yahoa.com",
            ]
        )

        self.assertIn("ocr_text_normalized", warnings)
        self.assertIn("Full Name: Caleb Chen", normalized)
        self.assertIn("Full Name: Emma Walker", normalized)
        self.assertIn("Date of Birth: 08/22/1948", normalized)
        self.assertIn("SSN: 971-96-8593", normalized)
        self.assertIn("Home Address: 4473 Riverview Avenue, Charlotte, NC 28203", normalized)
        self.assertIn("Personal Email: danielsingh@yahoo.com", normalized)
        self.assertIn("Personal Email: calebchen2@protonmail.com", normalized)
        self.assertIn("Personal Email: jack.foster6@gmail.com", normalized)
        self.assertIn("Personal Email: amelia.hughes@yahoo.com", normalized)
        self.assertIn("Diagnosis Code: E11.9", normalized)
        self.assertIn("Diagnosis Code: I10", normalized)
        self.assertIn("NDC: 00597-0087-17", normalized)
        self.assertIn("IBAN: FR1420041010050500013M02606", normalized)
        self.assertIn("Medicare Number: 5VX4TW6MK87", normalized)

    def test_mrn_validator_rejects_short_repeated_card_like_fragments(self) -> None:
        self.assertFalse(mrn_check("5555"))
        self.assertFalse(mrn_check("44444"))
        self.assertTrue(mrn_check("704889"))

    def test_extract_tsv_text_chooses_best_multi_pass_result(self) -> None:
        weak_primary = ExtractedText(
            text="DOB: 02/14/1986",
            extraction_method="ocr_tsv",
            parser="tesseract",
            ocr_used=True,
            ocr_page_count=1,
            ocr_avg_confidence=61.0,
            low_confidence_ocr=True,
        )
        weak_adaptive = ExtractedText(
            text="Full Name: Alice Nguyen",
            extraction_method="ocr_tsv",
            parser="tesseract",
            ocr_used=True,
            ocr_page_count=1,
            ocr_avg_confidence=68.0,
            low_confidence_ocr=True,
        )
        strong_psm4 = ExtractedText(
            text="Full Name: Alice Nguyen\nDOB: 02/14/1986\nHome Address: 10 Main Street, Austin, TX 78701",
            extraction_method="ocr_tsv",
            parser="tesseract",
            ocr_used=True,
            ocr_page_count=1,
            ocr_avg_confidence=79.0,
            low_confidence_ocr=False,
        )
        medium_psm11 = ExtractedText(
            text="Full Name: Alice Nguyen\nDOB: 02/14/1986",
            extraction_method="ocr_tsv",
            parser="tesseract",
            ocr_used=True,
            ocr_page_count=1,
            ocr_avg_confidence=75.0,
            low_confidence_ocr=False,
        )

        class TempDir:
            def cleanup(self) -> None:
                return None

        with (
            patch(
                "app.processing.extractors.ocr_layout.save_ocr_variants",
                return_value=(TempDir(), [("base", Path("base.png")), ("adaptive", Path("adaptive.png"))]),
            ),
            patch(
                "app.processing.extractors.ocr_layout._run_tesseract_tsv",
                side_effect=[weak_primary, weak_adaptive, strong_psm4, medium_psm11],
            ),
        ):
            extraction = extract_tsv_text(Path("fake.png"))

        self.assertEqual(strong_psm4.text, extraction.text)
        self.assertIn("ocr_variant_adaptive", extraction.warnings)
        self.assertIn("ocr_psm_4", extraction.warnings)

    def test_attachment_content_exposes_structured_metadata_for_xlsx(self) -> None:
        workbook = openpyxl.Workbook()
        worksheet = workbook.active
        worksheet.title = "Roster"
        worksheet.append(["full_name", "dob", "phone"])
        worksheet.append(["Alice Nguyen", "02/14/1986", "(212) 555-0189"])

        buffer = io.BytesIO()
        workbook.save(buffer)

        extraction = extract_attachment_content(
            Attachment(
                filename="roster.xlsx",
                mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                data=buffer.getvalue(),
                source_eml="email_001.eml",
            )
        )

        self.assertTrue(extraction.structured)
        self.assertEqual("spreadsheet_rows", extraction.extraction_method)
        self.assertEqual(1, extraction.table_count)
        self.assertIn("full name: Alice Nguyen", extraction.text)

    def test_nested_email_temp_file_is_cleaned_up(self) -> None:
        class FakeTempFile:
            name = "/tmp/fake_nested_email.eml"

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def write(self, data: bytes) -> None:
                self.data = data

            def flush(self) -> None:
                return None

        attachment = Attachment(
            filename="nested.eml",
            mime_type="message/rfc822",
            data=b"From: sender@example.com\nTo: review@example.com\nSubject: Nested\n\nBody",
            source_eml="email_001.eml",
        )

        with (
            patch("app.processing.attachment_handler.tempfile.NamedTemporaryFile", return_value=FakeTempFile()),
            patch(
                "app.processing.eml_parser.parse_eml_file",
                return_value={"body_text": "Nested body", "attachments": []},
            ),
            patch("app.processing.attachment_handler.os.unlink") as unlink_mock,
        ):
            extraction = extract_attachment_content(attachment)

        self.assertIn("Nested body", extraction.text)
        unlink_mock.assert_called_once_with("/tmp/fake_nested_email.eml")

    def test_pdf_extractor_renders_tables_from_pdfplumber(self) -> None:
        class FakePage:
            def extract_text(self, layout=False):
                return "Summary page with enough machine text to avoid OCR fallback during the unit test."

            def extract_tables(self):
                return [[["Field", "Value"], ["Full Name", "Alice Nguyen"], ["DOB", "02/14/1986"]]]

        class FakePDF:
            pages = [FakePage()]

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        with patch("app.processing.extractors.pdf_extractor.pdfplumber.open", return_value=FakePDF()):
            extraction = extract_pdf_with_metadata(b"%PDF-1.7 fake")

        self.assertEqual(1, extraction.page_count)
        self.assertEqual(1, extraction.table_count)
        self.assertTrue(extraction.structured)
        self.assertIn("Full Name: Alice Nguyen", extraction.text)

    def test_low_confidence_ocr_blocks_auto_clear(self) -> None:
        class StubHelper(LocalLLMFileQAHelper):
            def _request_json(self, path: str, payload=None, method: str = "POST"):
                return {
                    "response": (
                        '{"needs_human_review": false, "confidence": 0.95, '
                        '"suspected_missing_types": [], "questionable_detected_types": [], '
                        '"evidence_quotes": [], "reason": "No material issues detected."}'
                    )
                }

        helper = StubHelper(enabled=True)
        result = EmailAnalysisResult(
            eml_filename="email_scan.eml",
            from_address="alerts@example.com",
            to_addresses=["review@example.com"],
            cc_addresses=[],
            bcc_addresses=[],
            subject="Scanned intake packet",
            source_extractions={
                "email_scan.eml > intake_packet.pdf": SourceExtractionMetadata(
                    source_ref="email_scan.eml > intake_packet.pdf",
                    extraction_method="pdf_layout_and_ocr",
                    parser="pdfplumber+pdftoppm+tesseract",
                    page_count=1,
                    structured=True,
                    ocr_used=True,
                    ocr_page_count=1,
                    ocr_avg_confidence=61.2,
                    low_confidence_ocr=True,
                    warnings=["low_confidence_ocr"],
                )
            },
        )

        review = helper.review_email_result(result)

        self.assertTrue(review.needs_human_review)
        self.assertEqual("needs_review", review.status)
        self.assertEqual("uncertain_extraction_quality", review.error)


if __name__ == "__main__":
    unittest.main()
