from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.benchmarking.fixtures import REALWORLD_V3_PROFILE, REALWORLD_V4_PROFILE
from app.benchmarking.generator import GROUND_TRUTH_FILENAME, REALWORLD_V2_PROFILE, generate_benchmark_dataset
from app.benchmarking.evaluator import evaluate_benchmark
from app.processing.pipeline import process_single_eml


class BenchmarkingHeavyTests(unittest.TestCase):
    """Slower benchmark-generation and end-to-end scoring coverage.

    These tests intentionally build richer synthetic datasets and are kept out of
    default unittest discovery so normal developer feedback stays fast.
    """

    def test_realworld_v2_profile_generates_diverse_parseable_records(self):
        with TemporaryDirectory() as temp_dir:
            dataset = generate_benchmark_dataset(Path(temp_dir), file_count=5, profile=REALWORLD_V2_PROFILE)

            self.assertEqual(dataset.name, "pii-breach-benchmark-realworld-v2")
            self.assertTrue((Path(temp_dir) / GROUND_TRUTH_FILENAME).exists())

            security_result = process_single_eml(Path(temp_dir) / "email_002.eml")
            self.assertIn("IPV4", {match.pii_type for match in security_result.pii_matches})

            mixed_result = process_single_eml(Path(temp_dir) / "email_004.eml")
            self.assertGreaterEqual(len(mixed_result.attachments_processed), 2)

            summary = evaluate_benchmark(Path(temp_dir), run_ai_qa=False)
            self.assertEqual(len(summary.files), 5)
            self.assertGreater(summary.deterministic_findings.expected, 0)
            self.assertIsNotNone(summary.end_to_end)
            self.assertGreater(summary.end_to_end.report_owner_file_type.expected, 0)

    def test_realworld_v3_profile_generates_attachment_first_records(self):
        with TemporaryDirectory() as temp_dir:
            dataset = generate_benchmark_dataset(Path(temp_dir), file_count=6, profile=REALWORLD_V3_PROFILE)

            self.assertEqual(dataset.name, "pii-breach-benchmark-realworld-v3")
            self.assertTrue(all(item.attachments for item in dataset.files))

            negative_result = process_single_eml(Path(temp_dir) / "email_001.eml")
            self.assertEqual(set(), {match.pii_type for match in negative_result.pii_matches})

            identity_result = process_single_eml(Path(temp_dir) / "email_002.eml")
            self.assertTrue(
                any(record.filename.endswith((".pdf", ".png", ".jpg")) for record in identity_result.attachments_processed)
            )
            self.assertIn("FULL_NAME", {match.pii_type for match in identity_result.pii_matches})

            household_result = process_single_eml(Path(temp_dir) / "email_006.eml")
            self.assertTrue(any(record.filename.endswith(".zip") for record in household_result.attachments_processed))
            summary = evaluate_benchmark(Path(temp_dir), run_ai_qa=False)
            self.assertEqual(len(summary.files), 6)
            self.assertGreater(summary.end_to_end.report_owner_file_type.expected, 0)

    def test_realworld_v4_profile_generates_challenge_packets(self):
        with TemporaryDirectory() as temp_dir:
            dataset = generate_benchmark_dataset(Path(temp_dir), file_count=12, profile=REALWORLD_V4_PROFILE)

            self.assertEqual(dataset.name, "pii-breach-benchmark-realworld-v4")
            self.assertTrue((Path(temp_dir) / GROUND_TRUTH_FILENAME).exists())

            negative_result = process_single_eml(Path(temp_dir) / "email_001.eml")
            self.assertEqual(set(), {match.pii_type for match in negative_result.pii_matches})
            self.assertGreaterEqual(len(negative_result.attachments_processed), 2)

            identity_result = process_single_eml(Path(temp_dir) / "email_002.eml")
            self.assertTrue(any(record.filename.endswith(".zip") for record in identity_result.attachments_processed))
            self.assertIn("FULL_NAME", {match.pii_type for match in identity_result.pii_matches})

            medical_result = process_single_eml(Path(temp_dir) / "email_005.eml")
            self.assertTrue(any(record.filename.endswith(".eml") for record in medical_result.attachments_processed))
            self.assertTrue({"MRN", "MEDICARE"} & {match.pii_type for match in medical_result.pii_matches})

            household_file = dataset.files[9 - 1]
            household_owners = {finding.entity_name for finding in household_file.expected_findings}
            self.assertEqual(2, len(household_owners))

            summary = evaluate_benchmark(Path(temp_dir), run_ai_qa=False)
            self.assertEqual(len(summary.files), 12)
            self.assertGreater(summary.end_to_end.report_owner_file_type.expected, 0)


if __name__ == "__main__":
    unittest.main()
