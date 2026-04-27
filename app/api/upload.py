import logging
import shutil
import uuid
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse

from app.api.upload_utils import sanitize_upload_filename, save_upload_file
from app.processing.job_manager import get_job_manager
from app.processing.pipeline import run_analysis_pipeline
from app.models import JobStatus, ProgressUpdate
from app.settings import MAX_FILE_SIZE_MB, UPLOAD_DIR
import asyncio

logger = logging.getLogger(__name__)

router = APIRouter()
job_manager = get_job_manager()


@router.post("/upload")
async def upload_files(files: list[UploadFile] = File(...)):
    """
    Upload .eml files for analysis.
    Returns job_id and initial status.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    validated_uploads: list[tuple[UploadFile, str]] = []
    invalid_filenames: list[str] = []
    for file in files:
        try:
            sanitized = sanitize_upload_filename(file.filename or "")
        except HTTPException:
            invalid_filenames.append(file.filename or "<missing filename>")
        else:
            validated_uploads.append((file, sanitized))

    if invalid_filenames:
        for file in files:
            await file.close()
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Only `.eml` files can be uploaded. Remove unsupported files and retry the full batch.",
                "invalid_filenames": invalid_filenames,
            },
        )

    if not validated_uploads:
        raise HTTPException(status_code=400, detail="No `.eml` files provided.")

    # Create upload directory
    job_id = str(uuid.uuid4())
    job_dir = Path(UPLOAD_DIR) / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    uploads_dir = job_dir / "uploads"
    uploads_dir.mkdir(exist_ok=True)

    # Save uploaded files
    saved_paths: list[Path] = []
    max_file_bytes = MAX_FILE_SIZE_MB * 1024 * 1024
    for file, sanitized_name in validated_uploads:
        try:
            file_path = await save_upload_file(file, uploads_dir, max_bytes=max_file_bytes, sanitized_filename=sanitized_name)
            saved_paths.append(file_path)
            logger.info(f"Saved uploaded file: {file_path}")
        except HTTPException:
            shutil.rmtree(job_dir, ignore_errors=True)
            raise
        except Exception as e:
            shutil.rmtree(job_dir, ignore_errors=True)
            logger.error(f"Error saving {file.filename}: {e}")
            raise HTTPException(status_code=500, detail=f"Error saving file: {str(e)}")

    # Create job state
    try:
        job_manager.create_job(job_id)
        job_manager.update_job_progress(
            job_id,
            ProgressUpdate(
                status="queued",
                processed=0,
                total=len(saved_paths),
                current_file="",
                persons_found=0,
                message="Upload complete. Waiting for an analysis worker slot.",
            ),
        )

        # Start analysis pipeline asynchronously
        asyncio.create_task(_run_pipeline_task(job_id, saved_paths, job_dir.parent))
    except Exception as exc:
        logger.error("Failed to initialize analysis job %s: %s", job_id, exc)
        shutil.rmtree(job_dir, ignore_errors=True)
        try:
            job_manager.delete_job(job_id)
        except Exception:
            logger.exception("Failed to roll back job state for %s after initialization failure.", job_id)
        raise HTTPException(status_code=500, detail="Could not initialize the analysis run.") from exc

    return JSONResponse(
        status_code=202,
        content={
            "job_id": job_id,
            "file_count": len(saved_paths),
            "status": "queued",
            "active_jobs": job_manager.active_job_count(),
            "queued_jobs": job_manager.queued_job_count(),
        }
    )


async def _run_pipeline_task(job_id: str, file_paths: list[Path], jobs_dir: Path) -> None:
    """Run analysis pipeline asynchronously"""
    acquired_slot = False
    try:
        await job_manager.acquire_execution_slot(job_id)
        acquired_slot = True
        job_manager.update_job_status(job_id, JobStatus.PROCESSING)
        job_manager.update_job_progress(
            job_id,
            ProgressUpdate(
                status="progress",
                processed=0,
                total=len(file_paths),
                current_file="",
                persons_found=0,
                message="Analysis worker acquired. Starting scan.",
            ),
        )

        summary = await asyncio.to_thread(_run_pipeline_thread_entry, job_id, file_paths, jobs_dir)

        # Update job with results
        job_manager.set_job_result(job_id, summary)

        logger.info(f"Pipeline completed for job {job_id}")
    except Exception as e:
        logger.error(f"Pipeline error for job {job_id}: {e}")
        job_manager.set_job_error(job_id, str(e))
    finally:
        if acquired_slot:
            job_manager.release_execution_slot(job_id)


def _make_progress_callback(job_id: str):
    """Create a progress callback function for the pipeline"""
    async def progress_callback(update: ProgressUpdate) -> None:
        job_manager.update_job_progress(job_id, update)
    return progress_callback


def _run_pipeline_thread_entry(job_id: str, file_paths: list[Path], jobs_dir: Path) -> dict:
    """Run the async pipeline in a worker thread so the main event loop remains responsive."""
    progress_cb = _make_progress_callback(job_id)
    return asyncio.run(run_analysis_pipeline(job_id, file_paths, progress_cb, jobs_dir))
