import io
from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import UTC, datetime, timedelta
import unittest

from fastapi import HTTPException, UploadFile

from app.api import upload as upload_api
from app.api.upload_utils import sanitize_upload_filename, save_upload_file, unique_upload_path
from app.models import AnalysisJobSummary, PersonRecord, ProgressUpdate
from app.processing.job_manager import JobManager


class UploadHardeningTests(unittest.IsolatedAsyncioTestCase):
    def test_sanitize_upload_filename_strips_path_components(self) -> None:
        self.assertEqual("payload.eml", sanitize_upload_filename("../../payload.eml"))
        self.assertEqual("quarterly_report.eml", sanitize_upload_filename("quarterly report.eml"))

    def test_unique_upload_path_avoids_collisions(self) -> None:
        with TemporaryDirectory() as temp_dir:
            uploads_dir = Path(temp_dir)
            original = uploads_dir / "payload.eml"
            original.write_text("x", encoding="utf-8")

            candidate = unique_upload_path(uploads_dir, "payload.eml")

            self.assertEqual("payload_2.eml", candidate.name)

    async def test_save_upload_file_rejects_oversized_payload_and_cleans_partial_file(self) -> None:
        with TemporaryDirectory() as temp_dir:
            uploads_dir = Path(temp_dir)
            upload = UploadFile(filename="oversized.eml", file=io.BytesIO(b"x" * 9))

            with self.assertRaises(HTTPException):
                await save_upload_file(upload, uploads_dir, max_bytes=8)

            self.assertFalse((uploads_dir / "oversized.eml").exists())

    async def test_upload_endpoint_rejects_mixed_batches_instead_of_silently_skipping(self) -> None:
        valid = UploadFile(filename="valid.eml", file=io.BytesIO(b"From: a@example.com\n\nBody"))
        invalid = UploadFile(filename="notes.txt", file=io.BytesIO(b"not-an-eml"))

        with self.assertRaises(HTTPException) as exc:
            await upload_api.upload_files(files=[valid, invalid])

        self.assertEqual(400, exc.exception.status_code)
        self.assertEqual(
            {
                "message": "Only `.eml` files can be uploaded. Remove unsupported files and retry the full batch.",
                "invalid_filenames": ["notes.txt"],
            },
            exc.exception.detail,
        )
        self.assertTrue(valid.file.closed)
        self.assertTrue(invalid.file.closed)

    async def test_upload_endpoint_cleans_saved_files_if_job_initialization_fails(self) -> None:
        fixed_job_id = "job-init-failure"
        valid = UploadFile(filename="valid.eml", file=io.BytesIO(b"From: a@example.com\n\nBody"))

        with TemporaryDirectory() as temp_dir:
            with unittest.mock.patch.object(upload_api, "UPLOAD_DIR", temp_dir):
                with unittest.mock.patch.object(upload_api.uuid, "uuid4", return_value=fixed_job_id):
                    with unittest.mock.patch.object(upload_api.job_manager, "create_job", side_effect=RuntimeError("boom")):
                        with self.assertRaises(HTTPException) as exc:
                            await upload_api.upload_files(files=[valid])

        self.assertEqual(500, exc.exception.status_code)
        self.assertFalse((Path(temp_dir) / fixed_job_id).exists())

    async def test_job_manager_tracks_queued_and_active_jobs(self) -> None:
        with TemporaryDirectory() as temp_dir:
            manager = JobManager(upload_dir=Path(temp_dir), load_persisted=False)
            manager.create_job("job-a")

            self.assertEqual(1, manager.queued_job_count())
            self.assertEqual(0, manager.active_job_count())

            await manager.acquire_execution_slot("job-a")
            self.assertEqual(0, manager.queued_job_count())
            self.assertEqual(1, manager.active_job_count())

            manager.release_execution_slot("job-a")
            self.assertEqual(0, manager.active_job_count())

    def test_job_manager_lists_jobs_newest_first(self) -> None:
        with TemporaryDirectory() as temp_dir:
            manager = JobManager(upload_dir=Path(temp_dir), load_persisted=False)
            now = datetime.now(UTC)

            oldest = manager.create_job("job-oldest")
            middle = manager.create_job("job-middle")
            newest = manager.create_job("job-newest")

            oldest.created_at = now - timedelta(hours=2)
            middle.created_at = now - timedelta(hours=1)
            newest.created_at = now

            self.assertEqual(
                ["job-newest", "job-middle", "job-oldest"],
                [job.job_id for job in manager.list_jobs()],
            )

    def test_job_manager_reloads_completed_jobs_from_disk(self) -> None:
        with TemporaryDirectory() as temp_dir:
            upload_dir = Path(temp_dir)
            job_id = "job-persisted"
            job_dir = upload_dir / job_id / "reports"
            job_dir.mkdir(parents=True, exist_ok=True)
            (job_dir / "report.html").write_text("<html></html>", encoding="utf-8")
            (job_dir / "report.csv").write_text("header\n", encoding="utf-8")
            (job_dir / "file_review.csv").write_text("header\n", encoding="utf-8")

            manager = JobManager(upload_dir=upload_dir, load_persisted=False)
            manager.create_job(job_id)
            manager.update_job_progress(
                job_id,
                ProgressUpdate(
                    status="progress",
                    processed=3,
                    total=3,
                    current_file="email_003.eml",
                    persons_found=1,
                    message="Analysis complete",
                ),
            )
            manager.set_job_result(
                job_id,
                AnalysisJobSummary(
                    job_id=job_id,
                    total_files_processed=3,
                    total_persons_affected=1,
                    persons_high_risk=1,
                    persons_medium_risk=0,
                    persons_notification_required=1,
                    persons=[
                        PersonRecord(
                            person_id="person-1",
                            canonical_email="a@example.com",
                            canonical_name="A Example",
                            pii_matches=[object(), object()],
                            source_emails=["email_001.eml"],
                            highest_risk_level="HIGH",
                            notification_required=True,
                        )
                    ],
                    html_report=str(job_dir / "report.html"),
                    csv_report=str(job_dir / "report.csv"),
                    file_review_csv=str(job_dir / "file_review.csv"),
                    file_review_expected=True,
                    file_review_available=True,
                    build_id="build-1",
                    build_label="1.0.0+build-1",
                    html_report_schema_version="html-v1",
                    csv_report_schema_version="csv-v1",
                    file_review_schema_version="qa-v1",
                    files_ai_reviewed=3,
                    files_needing_human_review=1,
                ),
            )

            reloaded = JobManager(upload_dir=upload_dir, load_persisted=True)
            job = reloaded.get_job(job_id)

            self.assertIsNotNone(job)
            assert job is not None
            self.assertEqual("complete", job.status.value)
            self.assertIsNotNone(job.result_summary)
            self.assertEqual(3, job.result_summary.total_files_processed)
            self.assertEqual("A Example", job.result_summary.persons[0].canonical_name)

    def test_job_manager_delete_job_removes_persisted_directory(self) -> None:
        with TemporaryDirectory() as temp_dir:
            upload_dir = Path(temp_dir)
            manager = JobManager(upload_dir=upload_dir, load_persisted=False)
            manager.create_job("job-delete")

            job_dir = upload_dir / "job-delete"
            self.assertTrue(job_dir.exists())

            manager.delete_job("job-delete")

            self.assertFalse(job_dir.exists())
            self.assertIsNone(manager.get_job("job-delete"))


if __name__ == "__main__":
    unittest.main()
