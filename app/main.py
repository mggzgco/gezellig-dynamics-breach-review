"""FastAPI application entrypoint.

Primary responsibilities:
- construct the web application and mount API routers
- expose lightweight health/build metadata for the UI
- own startup/shutdown lifecycle tasks like job cleanup
"""

import logging
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import upload, jobs, reports, setup
from app.processing.job_manager import get_job_manager
from app.processing.pipeline import shutdown_pipeline_executors
from app.runtime_metadata import APP_VERSION, CURRENT_BUILD_LABEL, get_runtime_metadata
from app.settings import LOCAL_LLM_ENABLED, LOCAL_LLM_FILE_QA_ENABLED, UPLOAD_DIR
from app.setup_runtime import get_setup_runtime_coordinator

logger = logging.getLogger(__name__)

NO_CACHE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context for app startup and shutdown"""
    # Startup
    logger.info("Starting Gezellig Dynamics Breach Review build=%s", CURRENT_BUILD_LABEL)

    # Create jobs directory if it doesn't exist
    Path(UPLOAD_DIR).mkdir(parents=True, exist_ok=True)

    # Prime the structured-generation readiness check once at startup when prerequisites exist.
    setup_runtime = get_setup_runtime_coordinator()
    await asyncio.to_thread(setup_runtime.prime_structured_generation_check)

    # Start background cleanup task
    job_manager = get_job_manager()
    cleanup_task = asyncio.create_task(job_manager.cleanup_expired_jobs(check_interval_seconds=3600))

    yield

    # Shutdown
    logger.info("Shutting down Gezellig Dynamics Breach Review")
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass
    shutdown_pipeline_executors()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Gezellig Dynamics Breach Review",
        description="Gezellig Dynamics breach review platform for analyzing leaked emails and attachments for PII exposure",
        version=APP_VERSION,
        lifespan=lifespan,
    )

    app.include_router(upload.router, prefix="/api", tags=["Upload"])
    app.include_router(jobs.router, prefix="/api", tags=["Jobs"])
    app.include_router(reports.router, prefix="/api", tags=["Reports"])
    app.include_router(setup.router, prefix="/api", tags=["Setup"])
    app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
    return app


_configure_logging()
app = create_app()


@app.get("/")
async def root():
    """Serve the main UI"""
    ui_file = Path(__file__).parent / "static" / "index.html"
    if ui_file.exists():
        return FileResponse(ui_file, headers=NO_CACHE_HEADERS)
    return {"message": "Gezellig Dynamics Breach Review API"}


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    metadata = get_runtime_metadata()
    metadata["status"] = "healthy"
    return metadata


@app.get("/api/build-info")
async def build_info():
    """Expose runtime build and schema information to the UI and startup checks."""
    payload = get_runtime_metadata()
    payload.update(
        {
            "local_llm_enabled": LOCAL_LLM_ENABLED,
            "file_review_expected": LOCAL_LLM_FILE_QA_ENABLED,
        }
    )
    return JSONResponse(content=payload, headers=NO_CACHE_HEADERS)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        log_level="info",
    )
