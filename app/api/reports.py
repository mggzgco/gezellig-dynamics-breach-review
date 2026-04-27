import logging
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.settings import UPLOAD_DIR

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/jobs/{job_id}/report.html")
async def download_html_report(job_id: str):
    """Download HTML report"""
    report_file = Path(UPLOAD_DIR) / job_id / "reports" / "report.html"

    if report_file.exists():
        return FileResponse(
            path=report_file,
            filename=f"breach_report_{job_id[:8]}.html",
            media_type="text/html",
        )

    raise HTTPException(status_code=404, detail="Report not found. Job may still be processing.")


@router.get("/jobs/{job_id}/report.csv")
async def download_csv_report(job_id: str):
    """Download CSV report"""
    report_file = Path(UPLOAD_DIR) / job_id / "reports" / "report.csv"

    if report_file.exists():
        return FileResponse(
            path=report_file,
            filename=f"breach_report_{job_id[:8]}.csv",
            media_type="text/csv",
        )

    raise HTTPException(status_code=404, detail="Report not found. Job may still be processing.")


@router.get("/jobs/{job_id}/file_review.csv")
async def download_file_review_csv(job_id: str):
    """Download file-level AI QA review CSV."""
    report_file = Path(UPLOAD_DIR) / job_id / "reports" / "file_review.csv"

    if report_file.exists():
        return FileResponse(
            path=report_file,
            filename=f"breach_file_review_{job_id[:8]}.csv",
            media_type="text/csv",
        )

    raise HTTPException(status_code=404, detail="File review report not found. Job may still be processing.")
