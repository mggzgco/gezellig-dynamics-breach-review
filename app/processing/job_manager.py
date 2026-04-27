import asyncio
import csv
import json
import logging
import shutil
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Optional

from app.models import AnalysisJobSummary, JobState, JobStatus, PersonRecord, ProgressUpdate
from app.settings import JOB_EXPIRY_HOURS, MAX_CONCURRENT_JOBS, UPLOAD_DIR

logger = logging.getLogger(__name__)

JOB_STATE_FILENAME = "job_state.json"


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _parse_datetime(value: str | None) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _isoformat(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    else:
        value = value.astimezone(UTC)
    return value.isoformat()


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _split_values(raw: str, delimiter: str) -> list[str]:
    return [part.strip() for part in raw.split(delimiter) if part.strip()]


def _summary_person_to_payload(person: PersonRecord) -> dict:
    return {
        "person_id": person.person_id,
        "canonical_name": person.canonical_name,
        "canonical_email": person.canonical_email,
        "entity_type": person.entity_type,
        "attribution_confidence": person.attribution_confidence,
        "attribution_methods": list(person.attribution_methods),
        "source_emails": list(person.source_emails),
        "risk_score": person.risk_score,
        "highest_risk_level": person.highest_risk_level,
        "notification_required": person.notification_required,
        "pii_count": len(person.pii_matches),
    }


def _summary_person_from_payload(payload: dict) -> PersonRecord:
    pii_count = _safe_int(payload.get("pii_count"), 0)
    return PersonRecord(
        person_id=payload.get("person_id", ""),
        canonical_email=payload.get("canonical_email"),
        canonical_name=payload.get("canonical_name"),
        entity_type=payload.get("entity_type", "PERSON"),
        attribution_confidence=_safe_float(payload.get("attribution_confidence")),
        attribution_methods=list(payload.get("attribution_methods") or []),
        pii_matches=[object() for _ in range(pii_count)],
        source_emails=list(payload.get("source_emails") or []),
        risk_score=_safe_float(payload.get("risk_score")),
        highest_risk_level=payload.get("highest_risk_level", "NONE"),
        notification_required=bool(payload.get("notification_required")),
    )


def _summary_to_payload(summary: AnalysisJobSummary) -> dict:
    return {
        "job_id": summary.job_id,
        "total_files_processed": summary.total_files_processed,
        "total_persons_affected": summary.total_persons_affected,
        "persons_high_risk": summary.persons_high_risk,
        "persons_medium_risk": summary.persons_medium_risk,
        "persons_notification_required": summary.persons_notification_required,
        "persons": [_summary_person_to_payload(person) for person in summary.persons],
        "html_report": summary.html_report,
        "csv_report": summary.csv_report,
        "file_review_csv": summary.file_review_csv,
        "file_review_expected": summary.file_review_expected,
        "file_review_available": summary.file_review_available,
        "build_id": summary.build_id,
        "build_label": summary.build_label,
        "html_report_schema_version": summary.html_report_schema_version,
        "csv_report_schema_version": summary.csv_report_schema_version,
        "file_review_schema_version": summary.file_review_schema_version,
        "files_ai_reviewed": summary.files_ai_reviewed,
        "files_needing_human_review": summary.files_needing_human_review,
        "files_with_followup_matches": summary.files_with_followup_matches,
        "files_with_low_confidence_ocr": summary.files_with_low_confidence_ocr,
    }


def _summary_from_payload(payload: dict) -> AnalysisJobSummary:
    return AnalysisJobSummary(
        job_id=payload.get("job_id", ""),
        total_files_processed=_safe_int(payload.get("total_files_processed")),
        total_persons_affected=_safe_int(payload.get("total_persons_affected")),
        persons_high_risk=_safe_int(payload.get("persons_high_risk")),
        persons_medium_risk=_safe_int(payload.get("persons_medium_risk")),
        persons_notification_required=_safe_int(payload.get("persons_notification_required")),
        persons=[_summary_person_from_payload(person) for person in payload.get("persons", [])],
        html_report=payload.get("html_report", ""),
        csv_report=payload.get("csv_report", ""),
        file_review_csv=payload.get("file_review_csv", ""),
        file_review_expected=bool(payload.get("file_review_expected")),
        file_review_available=bool(payload.get("file_review_available")),
        build_id=payload.get("build_id", ""),
        build_label=payload.get("build_label", ""),
        html_report_schema_version=payload.get("html_report_schema_version", ""),
        csv_report_schema_version=payload.get("csv_report_schema_version", ""),
        file_review_schema_version=payload.get("file_review_schema_version", ""),
        files_ai_reviewed=_safe_int(payload.get("files_ai_reviewed")),
        files_needing_human_review=_safe_int(payload.get("files_needing_human_review")),
        files_with_followup_matches=_safe_int(payload.get("files_with_followup_matches")),
        files_with_low_confidence_ocr=_safe_int(payload.get("files_with_low_confidence_ocr")),
    )


class JobManager:
    """Thread-safe job manager with on-disk persistence for run history."""

    def __init__(self, upload_dir: str | Path = UPLOAD_DIR, load_persisted: bool = True):
        self._jobs: dict[str, JobState] = {}
        self._lock = threading.RLock()
        self._execution_semaphore = asyncio.Semaphore(MAX_CONCURRENT_JOBS)
        self._queued_job_ids: set[str] = set()
        self._active_job_ids: set[str] = set()
        self._upload_dir = Path(upload_dir)
        self._upload_dir.mkdir(parents=True, exist_ok=True)
        if load_persisted:
            self._load_jobs_from_disk()

    def _job_dir(self, job_id: str) -> Path:
        return self._upload_dir / job_id

    def _job_state_path(self, job_id: str) -> Path:
        return self._job_dir(job_id) / JOB_STATE_FILENAME

    def _job_to_payload(self, job: JobState) -> dict:
        return {
            "job_id": job.job_id,
            "status": job.status.value,
            "created_at": _isoformat(job.created_at),
            "completed_at": _isoformat(job.completed_at),
            "error": job.error,
            "progress": {
                "status": job.progress.status,
                "processed": job.progress.processed,
                "total": job.progress.total,
                "current_file": job.progress.current_file,
                "persons_found": job.progress.persons_found,
                "message": job.progress.message,
            },
            "result_summary": _summary_to_payload(job.result_summary) if job.result_summary else None,
        }

    def _persist_job_state(self, job: JobState) -> None:
        path = self._job_state_path(job.job_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self._job_to_payload(job), indent=2), encoding="utf-8")

    def _load_jobs_from_disk(self) -> None:
        for job_dir in sorted(self._upload_dir.iterdir(), reverse=True):
            if not job_dir.is_dir():
                continue
            try:
                job = self._load_job_from_disk(job_dir)
            except Exception as exc:
                logger.warning("Failed to load persisted job %s: %s", job_dir.name, exc)
                continue
            if job is None:
                continue
            self._jobs[job.job_id] = job

    def _load_job_from_disk(self, job_dir: Path) -> Optional[JobState]:
        state_path = job_dir / JOB_STATE_FILENAME
        if state_path.exists():
            payload = json.loads(state_path.read_text(encoding="utf-8"))
            job = JobState(
                job_id=payload["job_id"],
                status=JobStatus(payload.get("status", JobStatus.ERROR.value)),
                progress=ProgressUpdate(**(payload.get("progress") or {"status": "queued"})),
                result_summary=_summary_from_payload(payload["result_summary"]) if payload.get("result_summary") else None,
                created_at=_parse_datetime(payload.get("created_at")) or datetime.fromtimestamp(job_dir.stat().st_ctime, tz=UTC),
                completed_at=_parse_datetime(payload.get("completed_at")),
                error=payload.get("error"),
            )
            if job.status in {JobStatus.QUEUED, JobStatus.PROCESSING}:
                job.status = JobStatus.ERROR
                job.completed_at = job.completed_at or _utcnow()
                job.error = job.error or "Run interrupted before completion."
                job.progress.message = job.progress.message or "Run interrupted before completion."
                self._persist_job_state(job)
            return job

        return self._load_legacy_job(job_dir)

    def _load_legacy_job(self, job_dir: Path) -> Optional[JobState]:
        summary = self._build_legacy_summary(job_dir)
        if summary is None:
            return None

        created_at = datetime.fromtimestamp(job_dir.stat().st_ctime, tz=UTC)
        completed_at = datetime.fromtimestamp(Path(summary.csv_report).stat().st_mtime, tz=UTC) if summary.csv_report else created_at
        job = JobState(
            job_id=job_dir.name,
            status=JobStatus.COMPLETE,
            progress=ProgressUpdate(
                status="complete",
                processed=summary.total_files_processed,
                total=summary.total_files_processed,
                current_file="",
                persons_found=summary.total_persons_affected,
                message="Loaded from saved reports.",
            ),
            result_summary=summary,
            created_at=created_at,
            completed_at=completed_at,
        )
        self._persist_job_state(job)
        return job

    def _build_legacy_summary(self, job_dir: Path) -> Optional[AnalysisJobSummary]:
        report_file = job_dir / "reports" / "report.csv"
        if not report_file.exists():
            return None

        rows = list(csv.DictReader(report_file.open(encoding="utf-8", newline="")))
        if not rows:
            return None

        report_row = rows[0]
        unique_people: dict[str, PersonRecord] = {}
        for row in rows:
            person_id = row.get("Person ID", "").strip()
            if not person_id or person_id in unique_people:
                continue
            pii_count = _safe_int(row.get("PII Matches"))
            unique_people[person_id] = PersonRecord(
                person_id=person_id,
                canonical_email=(row.get("Email Address") or "").strip() or None,
                canonical_name=(row.get("Name") or "").strip() or None,
                entity_type=(row.get("Entity Type") or "PERSON").strip(),
                attribution_confidence=_safe_float(row.get("Attribution Confidence")),
                attribution_methods=_split_values(row.get("Attribution Methods", ""), ","),
                pii_matches=[object() for _ in range(pii_count)],
                source_emails=_split_values(row.get("Entity Source Email Files", ""), "|"),
                risk_score=_safe_float(row.get("Risk Score")),
                highest_risk_level=(row.get("Risk Level") or "NONE").strip(),
                notification_required=(row.get("Notification Required") == "Y"),
            )

        file_review_file = job_dir / "reports" / "file_review.csv"
        files_ai_reviewed = 0
        files_needing_human_review = 0
        files_with_followup_matches = 0
        files_with_low_confidence_ocr = 0
        file_review_schema_version = ""
        if file_review_file.exists():
            review_rows = list(csv.DictReader(file_review_file.open(encoding="utf-8", newline="")))
            if review_rows:
                file_review_schema_version = review_rows[0].get("report_schema_version", "")
            for row in review_rows:
                if row.get("qa_reviewed") == "Y":
                    files_ai_reviewed += 1
                if row.get("qa_needs_human_review") == "Y":
                    files_needing_human_review += 1
                if _safe_int(row.get("qa_followup_match_count")) > 0:
                    files_with_followup_matches += 1
                if _safe_int(row.get("low_confidence_ocr_source_count")) > 0:
                    files_with_low_confidence_ocr += 1

        uploads_dir = job_dir / "uploads"
        total_files_processed = len(list(uploads_dir.glob("*.eml"))) if uploads_dir.exists() else len({row.get("Current Source Email File") for row in rows if row.get("Current Source Email File")})
        people = list(unique_people.values())

        return AnalysisJobSummary(
            job_id=job_dir.name,
            total_files_processed=total_files_processed,
            total_persons_affected=len(people),
            persons_high_risk=sum(1 for person in people if person.highest_risk_level in ("CRITICAL", "HIGH")),
            persons_medium_risk=sum(1 for person in people if person.highest_risk_level == "MEDIUM"),
            persons_notification_required=sum(1 for person in people if person.notification_required),
            persons=people,
            html_report=str(job_dir / "reports" / "report.html"),
            csv_report=str(report_file),
            file_review_csv=str(file_review_file),
            file_review_expected=file_review_file.exists(),
            file_review_available=file_review_file.exists(),
            build_id=report_row.get("Report Build ID", ""),
            build_label=report_row.get("Report Build ID", ""),
            html_report_schema_version=report_row.get("Report Schema Version", ""),
            csv_report_schema_version=report_row.get("Report Schema Version", ""),
            file_review_schema_version=file_review_schema_version,
            files_ai_reviewed=files_ai_reviewed,
            files_needing_human_review=files_needing_human_review,
            files_with_followup_matches=files_with_followup_matches,
            files_with_low_confidence_ocr=files_with_low_confidence_ocr,
        )

    def create_job(self, job_id: str) -> JobState:
        """Create a new job."""
        with self._lock:
            if job_id in self._jobs:
                raise ValueError(f"Job {job_id} already exists")

            job = JobState(
                job_id=job_id,
                status=JobStatus.QUEUED,
                progress=ProgressUpdate(status="queued"),
                created_at=_utcnow(),
            )
            self._jobs[job_id] = job
            self._queued_job_ids.add(job_id)
            self._persist_job_state(job)
            logger.info("Created job %s", job_id)
            return job

    def get_job(self, job_id: str) -> Optional[JobState]:
        with self._lock:
            return self._jobs.get(job_id)

    def list_jobs(self) -> list[JobState]:
        with self._lock:
            return sorted(
                self._jobs.values(),
                key=lambda job: (job.created_at, job.completed_at or job.created_at),
                reverse=True,
            )

    def update_job_status(self, job_id: str, status: JobStatus) -> None:
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id].status = status
                if status == JobStatus.COMPLETE:
                    self._jobs[job_id].completed_at = _utcnow()
                self._persist_job_state(self._jobs[job_id])

    def update_job_progress(self, job_id: str, progress: ProgressUpdate) -> None:
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id].progress = progress
                self._persist_job_state(self._jobs[job_id])

    def set_job_error(self, job_id: str, error: str) -> None:
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id].error = error
                self._jobs[job_id].status = JobStatus.ERROR
                self._jobs[job_id].completed_at = _utcnow()
                self._persist_job_state(self._jobs[job_id])

    def set_job_result(self, job_id: str, result_summary: AnalysisJobSummary) -> None:
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id].result_summary = result_summary
                self._jobs[job_id].status = JobStatus.COMPLETE
                self._jobs[job_id].completed_at = _utcnow()
                self._persist_job_state(self._jobs[job_id])

    async def acquire_execution_slot(self, job_id: str) -> None:
        await self._execution_semaphore.acquire()
        with self._lock:
            self._queued_job_ids.discard(job_id)
            self._active_job_ids.add(job_id)
            if job_id in self._jobs:
                self._persist_job_state(self._jobs[job_id])

    def release_execution_slot(self, job_id: str) -> None:
        should_release = False
        with self._lock:
            if job_id in self._active_job_ids:
                self._active_job_ids.remove(job_id)
                should_release = True
        if should_release:
            self._execution_semaphore.release()

    def delete_job(self, job_id: str) -> None:
        should_release = False
        job_dir = self._job_dir(job_id)
        with self._lock:
            if job_id in self._jobs:
                del self._jobs[job_id]
            self._queued_job_ids.discard(job_id)
            if job_id in self._active_job_ids:
                self._active_job_ids.remove(job_id)
                should_release = True
        if should_release:
            self._execution_semaphore.release()
        if job_dir.exists():
            try:
                shutil.rmtree(job_dir)
                logger.info("Deleted job directory %s", job_dir)
            except Exception as exc:
                logger.warning("Failed to delete job directory %s: %s", job_dir, exc)

    async def cleanup_expired_jobs(self, check_interval_seconds: int = 3600) -> None:
        while True:
            try:
                await asyncio.sleep(check_interval_seconds)
                now = _utcnow()
                expired_job_ids = []

                with self._lock:
                    for job_id, job in list(self._jobs.items()):
                        if job.completed_at:
                            age = now - job.completed_at.astimezone(UTC)
                            if age > timedelta(hours=JOB_EXPIRY_HOURS):
                                expired_job_ids.append(job_id)

                for job_id in expired_job_ids:
                    logger.info("Cleaning up expired job %s", job_id)
                    self.delete_job(job_id)
            except Exception as exc:
                logger.error("Error in cleanup_expired_jobs: %s", exc)

    def active_job_count(self) -> int:
        with self._lock:
            return len(self._active_job_ids)

    def queued_job_count(self) -> int:
        with self._lock:
            return len(self._queued_job_ids)


_job_manager: Optional[JobManager] = None


def get_job_manager() -> JobManager:
    global _job_manager
    if _job_manager is None:
        _job_manager = JobManager(load_persisted=True)
    return _job_manager
