"""Setup and onboarding endpoints for local runtime dependencies."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.setup_runtime import get_setup_runtime_coordinator


router = APIRouter()
setup_runtime = get_setup_runtime_coordinator()


@router.get("/setup/status")
async def get_setup_status():
    """Return lightweight onboarding status for the local runtime."""
    payload = await asyncio.to_thread(setup_runtime.get_status, deep=False)
    return JSONResponse(content=payload)


@router.post("/setup/system-check")
async def run_system_check():
    """Run a deeper system check including structured generation validation."""
    payload = await asyncio.to_thread(setup_runtime.get_status, deep=True)
    return JSONResponse(content=payload)


@router.post("/setup/start-ollama")
async def start_ollama_service():
    """Attempt to launch the local Ollama runtime in the background."""
    accepted, payload = await asyncio.to_thread(setup_runtime.start_ollama_service)
    return JSONResponse(status_code=202 if accepted else 409, content=payload)


@router.post("/setup/pull-model")
async def pull_recommended_model():
    """Start pulling the recommended local model in the background."""
    accepted, payload = await asyncio.to_thread(setup_runtime.start_model_pull)
    return JSONResponse(status_code=202 if accepted else 409, content=payload)


@router.post("/setup/install-dependency/{dependency}")
async def install_dependency(dependency: str):
    """Attempt a supported local dependency install through the startup wizard."""
    accepted, payload = await asyncio.to_thread(setup_runtime.start_dependency_install, dependency)
    return JSONResponse(status_code=202 if accepted else 409, content=payload)
