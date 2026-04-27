import unittest

from app.models import EmailAnalysisResult
from app.processing.person_resolver import resolve_persons
from app.processing.local_llm_attribution import LLMAttributionResponse
from app.processing.pii_engine import scan_text


class DisabledAttributionHelper:
    enabled = False

    def choose_candidate(self, attribution_request):  # pragma: no cover - defensive only
        return None


class EntityAttributionTests(unittest.TestCase):
    def _build_result(
        self,
        source_ref: str,
        text: str,
        *,
        from_address: str = "sender@example.com",
        to_addresses: list[str] | None = None,
        to_names: list[str] | None = None,
        subject: str = "Test",
    ) -> EmailAnalysisResult:
        return EmailAnalysisResult(
            eml_filename="sample.eml",
            from_address=from_address,
            to_addresses=to_addresses or [],
            cc_addresses=[],
            bcc_addresses=[],
            subject=subject,
            to_names=to_names or [],
            pii_matches=scan_text(text, source_ref),
            source_texts={source_ref: text},
        )

    def _resolve_persons(self, result: EmailAnalysisResult):
        return resolve_persons([result], llm_helper=DisabledAttributionHelper())

    def test_direct_notice_is_attributed_to_recipient(self):
        source_ref = "sample.eml (email body)"
        text = (
            "Dear Sarah Chen,\n"
            "Your package will arrive tomorrow.\n"
            "Address: 123 Riverside Drive, Portland, OR 97214\n"
            "Phone: 212-555-1212\n"
        )
        result = self._build_result(
            source_ref,
            text,
            to_addresses=["sarah.chen@company.com"],
            to_names=["Sarah Chen"],
        )

        persons = self._resolve_persons(result)

        self.assertEqual(1, len(persons))
        self.assertEqual("sarah.chen@company.com", persons[0].canonical_email)
        self.assertEqual("Sarah Chen", persons[0].canonical_name)
        self.assertGreater(persons[0].attribution_confidence, 0.75)

    def test_explicit_named_subject_wins_over_recipient(self):
        source_ref = "sample.eml (email body)"
        text = (
            "Employee: Jane Doe\n"
            "SSN: 321-54-9876\n"
            "DOB: 05/14/1985\n"
        )
        result = self._build_result(
            source_ref,
            text,
            to_addresses=["benefits.manager@company.com"],
            to_names=["Benefits Manager"],
        )

        persons = self._resolve_persons(result)

        self.assertEqual(1, len(persons))
        self.assertEqual("Jane Doe", persons[0].canonical_name)
        self.assertIsNone(persons[0].canonical_email)
        self.assertIn("same_block_label", persons[0].attribution_methods)

    def test_tabular_row_anchor_attributes_attachment_finding(self):
        source_ref = "sample.eml > roster.xlsx"
        text = "Jane Doe\tjane.doe@example.com\t321-54-9876"
        result = self._build_result(
            source_ref,
            text,
            to_addresses=["reviewer@company.com"],
            to_names=["Review Team"],
        )

        persons = self._resolve_persons(result)

        self.assertEqual(1, len(persons))
        self.assertEqual("jane.doe@example.com", persons[0].canonical_email)
        self.assertEqual("Jane Doe", persons[0].canonical_name)
        self.assertIn("tabular_row", persons[0].attribution_methods)

    def test_tabular_field_value_row_attributes_following_fields_to_named_subject(self):
        source_ref = "sample.eml > record.csv"
        text = (
            "Full Name\tDate of Birth\tMobile Phone\tHome Address\n"
            "Full Name: Noah Williams\tDate of Birth: 06/06/1972\tMobile Phone: (313) 555-4670\t"
            "Home Address: 4652 Oak St, Austin, TX 78704\n"
        )
        result = self._build_result(
            source_ref,
            text,
            to_addresses=["reviewer@company.com"],
            to_names=["Review Team"],
        )

        persons = self._resolve_persons(result)

        self.assertEqual(1, len(persons))
        self.assertEqual("Noah Williams", persons[0].canonical_name)
        self.assertNotEqual("Full Name", persons[0].canonical_name)
        self.assertEqual({"FULL_NAME", "DOB", "PHONE", "ADDRESS"}, {match.pii_type for match in persons[0].pii_matches})

    def test_quoted_record_lines_can_attribute_two_blocks_backward(self):
        source_ref = "sample.eml (email body)"
        text = (
            "----- Forwarded message -----\n"
            "> Full Name: Henry Robinson\n"
            "> VIN: 0BPP74L7ZWYY0P1X9\n"
            "> Home Address: 531 Pine Lane, Denver, CO 80203\n"
        )
        result = self._build_result(
            source_ref,
            text,
            to_addresses=["reviewer@company.com"],
            to_names=["Review Team"],
        )

        persons = self._resolve_persons(result)

        self.assertEqual(1, len(persons))
        self.assertEqual("Henry Robinson", persons[0].canonical_name)
        self.assertEqual({"FULL_NAME", "VIN", "ADDRESS"}, {match.pii_type for match in persons[0].pii_matches})

    def test_quoted_record_lines_can_attribute_three_blocks_backward(self):
        source_ref = "sample.eml (email body)"
        text = (
            "----- Forwarded message -----\n"
            "> Full Name: Grace Kim\n"
            "> DOB: 06/11/1957\n"
            "> Driver's License Number: GA9859400\n"
            "> Mobile Phone: (699) 555-9642\n"
        )
        result = self._build_result(
            source_ref,
            text,
            to_addresses=["reviewer@company.com"],
            to_names=["Review Team"],
        )

        persons = self._resolve_persons(result)

        self.assertEqual(1, len(persons))
        self.assertEqual("Grace Kim", persons[0].canonical_name)
        self.assertEqual({"FULL_NAME", "DOB", "DRIVERS_LICENSE", "PHONE"}, {match.pii_type for match in persons[0].pii_matches})

    def test_attachment_without_owner_stays_unattributed(self):
        source_ref = "sample.eml > passport-12345678.txt"
        text = "Attachment filename: passport-12345678.txt\nReference document only."
        result = self._build_result(
            source_ref,
            text,
            to_addresses=["traveler@example.com"],
            to_names=["Alex Traveler"],
        )

        persons = self._resolve_persons(result)

        self.assertEqual(1, len(persons))
        self.assertEqual("UNATTRIBUTED", persons[0].canonical_name)
        self.assertEqual("UNATTRIBUTED_BLOCK", persons[0].entity_type)
        self.assertEqual(0.0, persons[0].attribution_confidence)

    def test_local_llm_is_only_used_for_ambiguous_blocks(self):
        class RecordingHelper:
            def __init__(self):
                self.enabled = True
                self.calls = 0

            def choose_candidate(self, attribution_request):
                self.calls += 1
                alice_candidate = next(
                    candidate for candidate in attribution_request.candidates if candidate.canonical_name == "Alice Doe"
                )
                return LLMAttributionResponse(
                    candidate_id=alice_candidate.candidate_id,
                    confidence=0.91,
                    evidence_quotes=["Dependent: Alice Doe"],
                    reason="Dependent label is closest to the unlabeled contact fields.",
                    model="qwen3:4b",
                    raw_response='{"candidate_id":"C2"}',
                )

        source_ref = "sample.eml (email body)"
        text = (
            "Employee: Jane Doe\n"
            "Dependent: Alice Doe\n"
            "Phone: 212-555-1212\n"
            "Address: 123 Riverside Drive, Portland, OR 97214\n"
        )
        result = self._build_result(
            source_ref,
            text,
            to_addresses=["benefits.manager@company.com"],
            to_names=["Benefits Manager"],
        )

        helper = RecordingHelper()
        persons = resolve_persons([result], llm_helper=helper)

        self.assertEqual(1, helper.calls)
        self.assertEqual(1, len(persons))
        self.assertEqual("Alice Doe", persons[0].canonical_name)
        self.assertIn("hybrid_local_llm", persons[0].attribution_methods)
        self.assertEqual({"FULL_NAME", "PHONE", "ADDRESS"}, {match.pii_type for match in persons[0].pii_matches})

    def test_local_llm_invalid_choice_falls_back_to_deterministic_resolution(self):
        class InvalidHelper:
            def __init__(self):
                self.enabled = True

            def choose_candidate(self, attribution_request):
                return LLMAttributionResponse(
                    candidate_id="C9",
                    confidence=0.99,
                    evidence_quotes=["Dependent: Alice Doe"],
                    reason="Invalid candidate on purpose.",
                    model="qwen3:4b",
                    raw_response='{"candidate_id":"C9"}',
                )

        source_ref = "sample.eml (email body)"
        text = (
            "Employee: Jane Doe\n"
            "Dependent: Alice Doe\n"
            "Phone: 212-555-1212\n"
        )
        result = self._build_result(
            source_ref,
            text,
            to_addresses=["benefits.manager@company.com"],
            to_names=["Benefits Manager"],
        )

        persons = resolve_persons([result], llm_helper=InvalidHelper())

        self.assertEqual(2, len(persons))
        by_name = {person.canonical_name: person for person in persons}
        self.assertEqual({"Alice Doe", "Jane Doe"}, set(by_name))
        self.assertEqual({"FULL_NAME"}, {match.pii_type for match in by_name["Alice Doe"].pii_matches})
        self.assertEqual({"FULL_NAME", "PHONE"}, {match.pii_type for match in by_name["Jane Doe"].pii_matches})
        self.assertNotIn("hybrid_local_llm", by_name["Jane Doe"].attribution_methods)

    def test_direct_notice_does_not_burn_llm_budget(self):
        class RecordingHelper:
            def __init__(self):
                self.enabled = True
                self.calls = 0

            def choose_candidate(self, attribution_request):
                self.calls += 1
                return None

        source_ref = "sample.eml (email body)"
        text = (
            "Dear Sarah Chen,\n"
            "Your package will arrive tomorrow.\n"
            "Address: 123 Riverside Drive, Portland, OR 97214\n"
        )
        result = self._build_result(
            source_ref,
            text,
            to_addresses=["sarah.chen@company.com"],
            to_names=["Sarah Chen"],
        )

        helper = RecordingHelper()
        persons = resolve_persons([result], llm_helper=helper)

        self.assertEqual(0, helper.calls)
        self.assertEqual("Sarah Chen", persons[0].canonical_name)
        self.assertEqual("sarah.chen@company.com", persons[0].canonical_email)

    def test_generic_role_email_does_not_self_identify_as_person(self):
        source_ref = "sample.eml (email body)"
        text = (
            "Operations review team,\n"
            "----- Forwarded message -----\n"
            "From: ops@healthsystem.org\n"
        )
        result = self._build_result(
            source_ref,
            text,
            to_addresses=["reviewer@company.com"],
            to_names=["Review Team"],
        )

        persons = self._resolve_persons(result)

        self.assertEqual([], persons)


if __name__ == "__main__":
    unittest.main()
