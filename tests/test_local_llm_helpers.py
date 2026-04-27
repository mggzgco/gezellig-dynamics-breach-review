import unittest

from app.models import EmailAnalysisResult, FileQAReview, SourceExtractionMetadata
from app.processing.local_llm_attribution import LocalLLMAttributionHelper
from app.processing.local_llm_file_qa import LocalLLMFileQAHelper
from app.processing.local_llm_file_qa_policy import should_review_result
from app.processing.pii_engine import scan_text
from app.processing.pipeline import _apply_bounded_qa_followup, _run_file_qa
from app.processing.pipeline_options import AnalysisPipelineOptions


class LocalLLMHelperTests(unittest.TestCase):
    def test_file_qa_parser_accepts_code_fenced_python_style_dict(self) -> None:
        helper = LocalLLMFileQAHelper(enabled=True)
        raw_text = """```json
{'needs_human_review': True, 'confidence': 0.81, 'suspected_missing_types': ['SSN'], 'questionable_detected_types': [], 'evidence_quotes': ['Employee SSN: 321-54-9876'], 'reason': 'Unlabeled identifier needs analyst confirmation.'}
```"""

        parsed = helper._extract_response_object(raw_text)

        self.assertIsNotNone(parsed)
        self.assertTrue(parsed["needs_human_review"])
        self.assertEqual(["SSN"], parsed["suspected_missing_types"])

    def test_file_qa_unparsable_output_falls_back_to_human_review(self) -> None:
        class StubHelper(LocalLLMFileQAHelper):
            def _request_json(self, path: str, payload=None, method: str = "POST"):
                return {"response": "not valid structured output"}

        helper = StubHelper(enabled=True, review_all_files=True)
        result = EmailAnalysisResult(
            eml_filename="email_001.eml",
            from_address="alerts@example.com",
            to_addresses=["case@example.com"],
            cc_addresses=[],
            bcc_addresses=[],
            subject="Review required",
        )

        review = helper.review_email_result(result)

        self.assertTrue(review.reviewed)
        self.assertTrue(review.used_model)
        self.assertTrue(review.needs_human_review)
        self.assertEqual("needs_review", review.status)

    def test_file_qa_request_failure_trips_circuit_breaker(self) -> None:
        class StubHelper(LocalLLMFileQAHelper):
            def __init__(self, **kwargs):
                super().__init__(**kwargs)
                self.request_count = 0

            def _request_json(self, path: str, payload=None, method: str = "POST"):
                self.request_count += 1
                raise RuntimeError("ollama unavailable")

        helper = StubHelper(enabled=True, review_all_files=True)
        result = EmailAnalysisResult(
            eml_filename="email_001.eml",
            from_address="alerts@example.com",
            to_addresses=["case@example.com"],
            cc_addresses=[],
            bcc_addresses=[],
            subject="Review required",
        )

        first_review = helper.review_email_result(result)
        second_review = helper.review_email_result(result)

        self.assertEqual(1, helper.request_count)
        self.assertEqual("error", first_review.status)
        self.assertTrue(first_review.needs_human_review)
        self.assertEqual("error", second_review.status)
        self.assertEqual("local_ai_qa_unavailable", second_review.error)

    def test_file_qa_truncated_json_is_salvaged(self) -> None:
        class StubHelper(LocalLLMFileQAHelper):
            def _request_json(self, path: str, payload=None, method: str = "POST"):
                return {
                    "response": (
                        '{'
                        '"needs_human_review": false,'
                        '"confidence": 0.98,'
                        '"suspected_missing_types": [],'
                        '"questionable_detected_types": [],'
                        '"evidence_quotes": ["No customer or employee record should be present"],'
                        '"reason": "The deterministic scan appears correct'
                    )
                }

        helper = StubHelper(enabled=True, review_all_files=True)
        result = EmailAnalysisResult(
            eml_filename="email_001.eml",
            from_address="alerts@example.com",
            to_addresses=["case@example.com"],
            cc_addresses=[],
            bcc_addresses=[],
            subject="Operational review",
            source_texts={"email_001.eml (email body)": "No customer or employee record should be present"},
        )

        review = helper.review_email_result(result)

        self.assertTrue(review.reviewed)
        self.assertTrue(review.used_model)
        self.assertFalse(review.needs_human_review)
        self.assertEqual("clear", review.status)

    def test_file_qa_uses_tighter_generation_budget_and_keep_alive(self) -> None:
        captured = {}

        class StubHelper(LocalLLMFileQAHelper):
            def _request_json(self, path: str, payload=None, method: str = "POST"):
                captured["path"] = path
                captured["payload"] = payload
                return {
                    "response": (
                        '{"needs_human_review": false, "confidence": 0.97, '
                        '"suspected_missing_types": [], "questionable_detected_types": [], '
                        '"evidence_quotes": ["Operational review only"], "reason": "Deterministic findings appear complete."}'
                    )
                }

        helper = StubHelper(enabled=True, review_all_files=True, num_predict=112, keep_alive="15m")
        result = EmailAnalysisResult(
            eml_filename="email_001.eml",
            from_address="alerts@example.com",
            to_addresses=["case@example.com"],
            cc_addresses=[],
            bcc_addresses=[],
            subject="Operational review",
            source_texts={"email_001.eml (email body)": "Operational review only"},
        )

        helper.review_email_result(result)

        self.assertEqual("/api/generate", captured["path"])
        self.assertEqual(112, captured["payload"]["options"]["num_predict"])
        self.assertEqual("15m", captured["payload"]["keep_alive"])

    def test_file_qa_record_like_attachment_without_findings_forces_review(self) -> None:
        class StubHelper(LocalLLMFileQAHelper):
            def _request_json(self, path: str, payload=None, method: str = "POST"):
                return {
                    "response": (
                        '{"needs_human_review": false, "confidence": 0.97, '
                        '"suspected_missing_types": [], "questionable_detected_types": [], '
                        '"evidence_quotes": [], "reason": "No deterministic findings detected."}'
                    )
                }

        helper = StubHelper(enabled=True)
        result = EmailAnalysisResult(
            eml_filename="email_103.eml",
            from_address="alerts@example.com",
            to_addresses=["case@example.com"],
            cc_addresses=[],
            bcc_addresses=[],
            subject="Record Verification Required",
            attachments_processed=[{"filename": "review_packet_103.zip", "mime_type": "application/zip"}],
        )

        review = helper.review_email_result(result)

        self.assertTrue(review.needs_human_review)
        self.assertEqual("needs_review", review.status)
        self.assertEqual("record_attachment_zero_findings", review.error)

    def test_operational_scanned_packet_without_findings_is_not_reviewed_by_default(self) -> None:
        result = EmailAnalysisResult(
            eml_filename="email_001.eml",
            from_address="alerts@example.com",
            to_addresses=["case@example.com"],
            cc_addresses=[],
            bcc_addresses=[],
            subject="Order Status Update #CLM-556789",
            attachments_processed=[
                {"filename": "ops_packet_001.png", "mime_type": "image/png"},
                {"filename": "ops_checklist_001.xlsx", "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
            ],
            source_extractions={
                "email_001.eml > ops_packet_001.png": SourceExtractionMetadata(
                    source_ref="email_001.eml > ops_packet_001.png",
                    extraction_method="ocr_tsv",
                    parser="tesseract",
                    ocr_used=True,
                    ocr_page_count=1,
                    ocr_avg_confidence=88.0,
                    structured=False,
                )
            },
            source_texts={
                "email_001.eml > ops_packet_001.png": (
                    "Internal Change-Control Snapshot\n"
                    "Ticket reference: CLM-556789\n"
                    "Support inbox: benefits@company.com\n"
                    "Source IP: 203.27.81.190\n"
                )
            },
        )

        self.assertFalse(should_review_result(result, review_all_files=False))

    def test_file_qa_labeled_email_gap_forces_review_even_if_model_clears(self) -> None:
        class StubHelper(LocalLLMFileQAHelper):
            def _request_json(self, path: str, payload=None, method: str = "POST"):
                return {
                    "response": (
                        '{"needs_human_review": false, "confidence": 0.95, '
                        '"suspected_missing_types": [], "questionable_detected_types": [], '
                        '"evidence_quotes": [], "reason": "All findings match expected patterns in source context."}'
                    )
                }

        source_ref = "email_027.eml > identity_archive_027.zip"
        text = (
            "Identity Archive Capture\n"
            "Full Name: Ava Price\n"
            "DOB: 08/22/1981\n"
            "Home Address: 3299 Oak Lane, Richmond, VA 23220\n"
            "Personal Email: @outlook.com\n"
            "Mobile Phone: (300) 555-2537\n"
        )
        result = EmailAnalysisResult(
            eml_filename="email_027.eml",
            from_address="alerts@example.com",
            to_addresses=["case@example.com"],
            cc_addresses=[],
            bcc_addresses=[],
            subject="Archive Identity Evidence Review",
            pii_matches=scan_text(text, source_ref),
            source_texts={source_ref: text},
            source_extractions={
                source_ref: SourceExtractionMetadata(
                    source_ref=source_ref,
                    extraction_method="ocr_tsv",
                    parser="tesseract",
                    ocr_used=True,
                    ocr_page_count=1,
                    ocr_avg_confidence=84.0,
                    structured=True,
                )
            },
            attachments_processed=[{"filename": "identity_archive_027.zip", "mime_type": "application/zip"}],
        )

        review = StubHelper(enabled=True).review_email_result(result)

        self.assertTrue(review.needs_human_review)
        self.assertEqual("needs_review", review.status)
        self.assertEqual("policy_review_required", review.error)

    def test_file_qa_labeled_iban_gap_forces_review_even_if_model_clears(self) -> None:
        class StubHelper(LocalLLMFileQAHelper):
            def _request_json(self, path: str, payload=None, method: str = "POST"):
                return {
                    "response": (
                        '{"needs_human_review": false, "confidence": 0.95, '
                        '"suspected_missing_types": [], "questionable_detected_types": [], '
                        '"evidence_quotes": [], "reason": "All findings match expected patterns in source context."}'
                    )
                }

        source_ref = "email_090.eml > payment_packet_090.zip"
        text = (
            "Payment Exception Backup\n"
            "Full Name: Jack Foster\n"
            "IBAN: FR14 2004 1010 0505 0001 3102 606\n"
            "Home Address: 4630 Pine Rd, Minneapolis, MN 55408\n"
            "Personal Email: jack.foster6 @g mai Lcom\n"
        )
        result = EmailAnalysisResult(
            eml_filename="email_090.eml",
            from_address="alerts@example.com",
            to_addresses=["case@example.com"],
            cc_addresses=[],
            bcc_addresses=[],
            subject="Payment Exception Packet",
            pii_matches=scan_text(text, source_ref),
            source_texts={source_ref: text},
            source_extractions={
                source_ref: SourceExtractionMetadata(
                    source_ref=source_ref,
                    extraction_method="pdf_layout_and_ocr",
                    parser="pdfplumber+pdftoppm+tesseract",
                    ocr_used=True,
                    ocr_page_count=1,
                    ocr_avg_confidence=80.0,
                    structured=True,
                )
            },
            attachments_processed=[{"filename": "payment_packet_090.zip", "mime_type": "application/zip"}],
        )

        review = StubHelper(enabled=True).review_email_result(result)

        self.assertTrue(review.needs_human_review)
        self.assertEqual("needs_review", review.status)
        self.assertEqual("policy_review_required", review.error)

    def test_file_qa_security_alert_case_can_clear_when_model_clears_and_extraction_is_clean(self) -> None:
        class StubHelper(LocalLLMFileQAHelper):
            def _request_json(self, path: str, payload=None, method: str = "POST"):
                return {
                    "response": (
                        '{"needs_human_review": false, "confidence": 0.97, '
                        '"suspected_missing_types": [], "questionable_detected_types": [], '
                        '"evidence_quotes": [], "reason": "Deterministic findings appear complete."}'
                    )
                }

        source_ref = "email_040.eml (email body)"
        text = (
            "User profile snapshot:\n"
            "Full Name: Jack Foster\n"
            "Login IP Address: 39.30.160.32\n"
            "Personal Email: jack.foster2@gmail.com\n"
            "Mobile Phone: (282) 555-5110\n"
        )
        result = EmailAnalysisResult(
            eml_filename="email_040.eml",
            from_address="alerts@example.com",
            to_addresses=["case@example.com"],
            cc_addresses=[],
            bcc_addresses=[],
            subject="Suspicious Login Validation",
            pii_matches=scan_text(text, source_ref),
            source_texts={source_ref: text},
        )

        review = StubHelper(enabled=True, review_all_files=True).review_email_result(result)

        self.assertFalse(review.needs_human_review)
        self.assertEqual("clear", review.status)
        self.assertIsNone(review.error)

    def test_file_qa_forwarded_record_case_can_clear_when_model_clears_and_extraction_is_clean(self) -> None:
        class StubHelper(LocalLLMFileQAHelper):
            def _request_json(self, path: str, payload=None, method: str = "POST"):
                return {
                    "response": (
                        '{"needs_human_review": false, "confidence": 0.97, '
                        '"suspected_missing_types": [], "questionable_detected_types": [], '
                        '"evidence_quotes": [], "reason": "Deterministic findings appear complete."}'
                    )
                }

        source_ref = "email_063.eml (email body)"
        text = (
            "Forwarding the quoted intake excerpt.\n"
            "----- Original Message -----\n"
            "> Full Name: Henry Robinson\n"
            "> Home Address: 531 Pine Lane, Denver, CO 80203\n"
        )
        result = EmailAnalysisResult(
            eml_filename="email_063.eml",
            from_address="alerts@example.com",
            to_addresses=["case@example.com"],
            cc_addresses=[],
            bcc_addresses=[],
            subject="Fwd: Record Verification Required",
            pii_matches=scan_text(text, source_ref),
            source_texts={source_ref: text},
        )

        review = StubHelper(enabled=True, review_all_files=True).review_email_result(result)

        self.assertFalse(review.needs_human_review)
        self.assertEqual("clear", review.status)
        self.assertIsNone(review.error)

    def test_file_qa_multi_entity_case_still_forces_review_even_if_model_clears(self) -> None:
        class StubHelper(LocalLLMFileQAHelper):
            def _request_json(self, path: str, payload=None, method: str = "POST"):
                return {
                    "response": (
                        '{"needs_human_review": false, "confidence": 0.97, '
                        '"suspected_missing_types": [], "questionable_detected_types": [], '
                        '"evidence_quotes": [], "reason": "Deterministic findings appear complete."}'
                    )
                }

        source_ref = "email_127.eml > household_127.csv"
        text = (
            "Primary Full Name: Ava Price\n"
            "Primary SSN: 123-45-6789\n"
            "Dependent Full Name: Olivia Price\n"
            "Dependent SSN: 987-65-4321\n"
            "Relationship: Dependent\n"
        )
        result = EmailAnalysisResult(
            eml_filename="email_127.eml",
            from_address="alerts@example.com",
            to_addresses=["case@example.com"],
            cc_addresses=[],
            bcc_addresses=[],
            subject="Household Coverage Review",
            pii_matches=scan_text(text, source_ref),
            source_texts={source_ref: text},
            attachments_processed=[{"filename": "household_127.csv", "mime_type": "text/csv"}],
        )

        review = StubHelper(enabled=True, review_all_files=True).review_email_result(result)

        self.assertTrue(review.needs_human_review)
        self.assertEqual("needs_review", review.status)
        self.assertEqual("policy_review_required", review.error)

    def test_should_review_result_still_runs_qa_for_security_alert_case(self) -> None:
        source_ref = "email_040.eml (email body)"
        text = (
            "User profile snapshot:\n"
            "Full Name: Jack Foster\n"
            "Login IP Address: 39.30.160.32\n"
            "Personal Email: jack.foster2@gmail.com\n"
            "Mobile Phone: (282) 555-5110\n"
        )
        result = EmailAnalysisResult(
            eml_filename="email_040.eml",
            from_address="alerts@example.com",
            to_addresses=["case@example.com"],
            cc_addresses=[],
            bcc_addresses=[],
            subject="Suspicious Login Validation",
            pii_matches=scan_text(text, source_ref),
            source_texts={source_ref: text},
        )

        self.assertTrue(should_review_result(result, review_all_files=False))

    def test_bounded_followup_scan_adds_targeted_deterministic_matches(self) -> None:
        result = EmailAnalysisResult(
            eml_filename="email_900.eml",
            from_address="alerts@example.com",
            to_addresses=["case@example.com"],
            cc_addresses=[],
            bcc_addresses=[],
            subject="Account verification",
            source_texts={
                "email_900.eml (email body)": (
                    "Emergency contact details are below.\n"
                    + ("filler text " * 60)
                    + "\n212-555-0189"
                )
            },
            qa_review=FileQAReview(
                reviewed=True,
                used_model=True,
                status="needs_review",
                needs_human_review=True,
                confidence=0.81,
                suspected_missing_types=["PHONE"],
                reason="Potential missed phone number.",
            ),
        )

        _apply_bounded_qa_followup(result)

        self.assertEqual(["PHONE"], sorted({match.pii_type for match in result.pii_matches}))
        self.assertTrue(result.qa_review.followup_scanned)
        self.assertEqual(1, result.qa_review.followup_match_count)
        self.assertEqual(["PHONE"], result.qa_review.followup_pii_types)

    def test_bounded_followup_infers_missing_types_from_record_like_ocr_text(self) -> None:
        result = EmailAnalysisResult(
            eml_filename="email_129.eml",
            from_address="alerts@example.com",
            to_addresses=["case@example.com"],
            cc_addresses=[],
            bcc_addresses=[],
            subject="Scanned intake packet",
            source_texts={
                "email_129.eml > intake_packet.pdf": (
                    "Full Name: Caleb Chen\n"
                    "Date of Birth: 04/18/1975\n"
                    "SSN: 371-96-8593\n"
                    "Home Address: 4473 Riverview Avenue, Charlotte, NC 28203\n"
                )
            },
            qa_review=FileQAReview(
                reviewed=True,
                used_model=True,
                status="needs_review",
                needs_human_review=True,
                confidence=0.71,
                suspected_missing_types=[],
                reason="Scanned packet likely contains missed identifiers.",
                evidence_quotes=["Caleb Chen"],
            ),
        )

        _apply_bounded_qa_followup(result)

        self.assertTrue(result.qa_review.followup_scanned)
        self.assertEqual(
            ["ADDRESS", "DOB", "FULL_NAME", "SSN"],
            sorted({match.pii_type for match in result.pii_matches}),
        )
        self.assertEqual(4, result.qa_review.followup_match_count)
        self.assertEqual(
            ["ADDRESS", "DOB", "FULL_NAME", "SSN"],
            result.qa_review.followup_pii_types,
        )

    def test_bounded_followup_uses_ai_evidence_quotes_to_infer_missing_type(self) -> None:
        result = EmailAnalysisResult(
            eml_filename="email_901.eml",
            from_address="alerts@example.com",
            to_addresses=["case@example.com"],
            cc_addresses=[],
            bcc_addresses=[],
            subject="Scanned intake packet",
            source_texts={
                "email_901.eml > intake_packet.pdf": "Employee identifier: 371-96-8593\n",
            },
            qa_review=FileQAReview(
                reviewed=True,
                used_model=True,
                status="needs_review",
                needs_human_review=True,
                confidence=0.68,
                suspected_missing_types=[],
                evidence_quotes=["SSN: 371-96-8593"],
                reason="Potential SSN detected in the scanned packet.",
            ),
        )

        _apply_bounded_qa_followup(result)

        self.assertTrue(result.qa_review.followup_scanned)
        self.assertEqual(["SSN"], sorted({match.pii_type for match in result.pii_matches}))
        self.assertEqual(["SSN"], result.qa_review.followup_pii_types)

    def test_attribution_parser_accepts_code_fenced_python_style_dict(self) -> None:
        helper = LocalLLMAttributionHelper(enabled=True)
        raw_text = """```json
{'candidate_id': 'candidate-1', 'confidence': 0.77, 'evidence_quotes': ['Lucas Brooks'], 'reason': 'The name is explicitly labeled in the same block.'}
```"""

        parsed = helper._extract_response_object(raw_text)

        self.assertIsNotNone(parsed)
        self.assertEqual("candidate-1", parsed["candidate_id"])
        self.assertEqual(["Lucas Brooks"], parsed["evidence_quotes"])


class LocalLLMPipelineIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_parallel_file_qa_reuses_one_helper_instance(self) -> None:
        class CountingHelper(LocalLLMFileQAHelper):
            def __init__(self):
                super().__init__(enabled=True, review_all_files=True)
                self.review_calls = 0

            def review_email_result(self, result: EmailAnalysisResult) -> FileQAReview:
                self.review_calls += 1
                return FileQAReview(reviewed=False, used_model=False, status="not_run")

        created_helpers: list[CountingHelper] = []

        def helper_factory() -> CountingHelper:
            helper = CountingHelper()
            created_helpers.append(helper)
            return helper

        results = [
            EmailAnalysisResult(
                eml_filename=f"email_{index:03d}.eml",
                from_address="alerts@example.com",
                to_addresses=["case@example.com"],
                cc_addresses=[],
                bcc_addresses=[],
                subject="Review required",
            )
            for index in range(3)
        ]

        async def progress_callback(update) -> None:
            return None

        options = AnalysisPipelineOptions(file_qa_workers=2, file_qa_helper_factory=helper_factory)
        await _run_file_qa(results, progress_callback, options)

        self.assertEqual(1, len(created_helpers))
        self.assertEqual(3, created_helpers[0].review_calls)


if __name__ == "__main__":
    unittest.main()
