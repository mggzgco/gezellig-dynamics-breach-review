import logging
import json
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from app.models import AnalysisJobSummary
from app.processing.job_manager import get_job_manager

logger = logging.getLogger(__name__)

router = APIRouter()
job_manager = get_job_manager()


def _serialize_persons(persons: list) -> list[dict]:
    persons_data = []
    for person in persons:
        persons_data.append({
            "person_id": person.person_id,
            "canonical_name": person.canonical_name,
            "canonical_email": person.canonical_email,
            "entity_type": person.entity_type,
            "highest_risk_level": person.highest_risk_level,
            "risk_score": person.risk_score,
            "attribution_confidence": person.attribution_confidence,
            "pii_count": len(person.pii_matches),
            "notification_required": person.notification_required,
        })
    return persons_data


def _serialize_summary(summary: AnalysisJobSummary) -> dict:
    persons = summary.persons
    return {
        "type": "complete",
        "total_files_processed": summary.total_files_processed,
        "persons_found": summary.total_persons_affected,
        "high_risk": summary.persons_high_risk,
        "medium_risk": summary.persons_medium_risk,
        "notification_required": summary.persons_notification_required,
        "files_ai_reviewed": summary.files_ai_reviewed,
        "files_needing_human_review": summary.files_needing_human_review,
        "files_with_followup_matches": summary.files_with_followup_matches,
        "files_with_low_confidence_ocr": summary.files_with_low_confidence_ocr,
        "persons": _serialize_persons(persons),
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
    }


def _serialize_job(job) -> dict:
    summary = job.result_summary
    can_delete = job.status.value in {"complete", "error"}
    payload = {
        "job_id": job.job_id,
        "status": job.status.value,
        "created_at": job.created_at.isoformat(),
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "error": job.error,
        "can_delete": can_delete,
        "progress": {
            "processed": job.progress.processed,
            "total": job.progress.total,
            "current_file": job.progress.current_file,
            "persons_found": job.progress.persons_found,
            "message": job.progress.message,
        },
        "result_available": bool(summary),
    }
    if summary is not None:
        payload["summary"] = {
            "total_files_processed": summary.total_files_processed,
            "persons_found": summary.total_persons_affected,
            "high_risk": summary.persons_high_risk,
            "medium_risk": summary.persons_medium_risk,
            "notification_required": summary.persons_notification_required,
            "files_ai_reviewed": summary.files_ai_reviewed,
            "files_needing_human_review": summary.files_needing_human_review,
            "file_review_available": summary.file_review_available,
            "build_label": summary.build_label,
        }
    else:
        payload["summary"] = None
    return payload


@router.get("/jobs")
async def list_jobs():
    """List recent jobs for the review workspace history panel."""
    jobs = [_serialize_job(job) for job in job_manager.list_jobs()]
    return JSONResponse(
        content={
            "jobs": jobs,
            "active_jobs": job_manager.active_job_count(),
            "queued_jobs": job_manager.queued_job_count(),
        }
    )


@router.get("/jobs/{job_id}/status")
async def get_job_status(job_id: str):
    """Get current job status (polling endpoint)"""
    job = job_manager.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return JSONResponse(
        content={
            "job_id": job_id,
            "status": job.status.value,
            "progress": {
                "processed": job.progress.processed,
                "total": job.progress.total,
                "current_file": job.progress.current_file,
                "persons_found": job.progress.persons_found,
                "message": job.progress.message,
            },
            "error": job.error,
            "result_available": bool(job.result_summary),
            "active_jobs": job_manager.active_job_count(),
            "queued_jobs": job_manager.queued_job_count(),
        }
    )


@router.get("/jobs/{job_id}/result")
async def get_job_result(job_id: str):
    """Get completed job summary for polling-based clients."""
    job = job_manager.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if not job.result_summary:
        raise HTTPException(status_code=409, detail="Job is not complete yet")

    return JSONResponse(content=_serialize_summary(job.result_summary))


@router.delete("/jobs/{job_id}")
async def delete_job(job_id: str):
    """Delete a saved run and its persisted artifacts."""
    job = job_manager.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status.value not in {"complete", "error"}:
        raise HTTPException(
            status_code=409,
            detail="Only completed or failed runs can be deleted.",
        )

    job_manager.delete_job(job_id)
    return JSONResponse(content={"job_id": job_id, "deleted": True})


@router.get("/jobs/{job_id}/stream")
async def stream_job_progress(job_id: str):
    """Stream job progress via Server-Sent Events"""
    job = job_manager.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    async def event_generator():
        """Generate SSE events as job progresses"""
        last_status = None

        while True:
            job = job_manager.get_job(job_id)
            if not job:
                break

            current_status = job.status.value
            progress = job.progress

            # Send progress event
            event = {
                "type": "progress",
                "status": current_status,
                "processed": progress.processed,
                "total": progress.total,
                "current_file": progress.current_file,
                "persons_found": progress.persons_found,
                "message": progress.message,
            }
            yield f"data: {json.dumps(event)}\n\n"

            # Check if job is complete
            if current_status == "complete":
                summary = job.result_summary
                if summary is None:
                    event = {"type": "error", "message": "Job completed without a result summary."}
                else:
                    event = _serialize_summary(summary)
                yield f"data: {json.dumps(event)}\n\n"
                break
            elif current_status == "error":
                event = {
                    "type": "error",
                    "message": job.error or "Unknown error",
                }
                yield f"data: {json.dumps(event)}\n\n"
                break

            # Small sleep to avoid busy-waiting
            import asyncio
            await asyncio.sleep(0.5)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
