from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.benchmarking.evaluator import evaluate_benchmark
from app.benchmarking.generator import GROUND_TRUTH_FILENAME, generate_benchmark_dataset
from app.processing.pipeline import process_single_eml


class BenchmarkingTests(unittest.TestCase):
    def test_generated_body_record_is_detectable(self):
        with TemporaryDirectory() as temp_dir:
            dataset = generate_benchmark_dataset(Path(temp_dir), file_count=1, start_index=113)
            self.assertEqual(dataset.summary()["total_files"], 1)

            result = process_single_eml(Path(temp_dir) / "email_113.eml")
            pii_types = {match.pii_type for match in result.pii_matches}

            self.assertIn("SSN", pii_types)
            self.assertIn("DOB", pii_types)
            self.assertIn("ADDRESS", pii_types)
            self.assertIn("FULL_NAME", pii_types)

    def test_generated_attachment_and_archive_records_are_parseable(self):
        with TemporaryDirectory() as temp_dir:
            generate_benchmark_dataset(Path(temp_dir), file_count=2, start_index=178)
            attachment_result = process_single_eml(Path(temp_dir) / "email_178.eml")
            attachment_types = {match.pii_type for match in attachment_result.pii_matches}
            self.assertTrue(any(" > " in source_ref for source_ref in attachment_result.source_texts))
            self.assertIn("EMAIL", attachment_types)
            self.assertIn("PHONE", attachment_types)

        with TemporaryDirectory() as temp_dir:
            generate_benchmark_dataset(Path(temp_dir), file_count=1, start_index=256)
            archive_result = process_single_eml(Path(temp_dir) / "email_256.eml")
            archive_types = {match.pii_type for match in archive_result.pii_matches}
            self.assertTrue(any(item.filename.endswith(".zip") for item in archive_result.attachments_processed))
            self.assertIn("DOB", archive_types)
            self.assertIn("ADDRESS", archive_types)

        with TemporaryDirectory() as temp_dir:
            generate_benchmark_dataset(Path(temp_dir), file_count=1, start_index=257)
            nested_result = process_single_eml(Path(temp_dir) / "email_257.eml")
            nested_types = {match.pii_type for match in nested_result.pii_matches}
            self.assertTrue(any(item.filename.endswith(".eml") for item in nested_result.attachments_processed))
            self.assertIn("FULL_NAME", nested_types)

    def test_evaluator_reads_ground_truth_slice(self):
        with TemporaryDirectory() as temp_dir:
            generate_benchmark_dataset(Path(temp_dir), file_count=4, start_index=113)
            self.assertTrue((Path(temp_dir) / GROUND_TRUTH_FILENAME).exists())

            summary = evaluate_benchmark(Path(temp_dir), run_ai_qa=False, run_attribution_llm=False)

            self.assertEqual(len(summary.files), 4)
            self.assertGreater(summary.deterministic_findings.expected, 0)
            self.assertEqual(summary.ai_reviewed_files, [])
            self.assertIn("SSN", summary.by_type)
            self.assertIsNotNone(summary.end_to_end)
            self.assertFalse(summary.end_to_end.file_qa_enabled)
            self.assertFalse(summary.end_to_end.attribution_llm_enabled)
            self.assertGreater(summary.end_to_end.report_file_type.expected, 0)
            self.assertGreater(summary.end_to_end.report_owner_file_type.expected, 0)

    def test_generated_findings_include_owner_labels_for_multi_entity_cases(self):
        with TemporaryDirectory() as temp_dir:
            dataset = generate_benchmark_dataset(Path(temp_dir), file_count=1, start_index=281)
            owner_names = {finding.entity_name for finding in dataset.files[0].expected_findings}

        self.assertEqual(2, len(owner_names))
        self.assertNotIn(None, owner_names)


if __name__ == "__main__":
    unittest.main()
