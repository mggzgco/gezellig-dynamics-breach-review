#!/usr/bin/env python3
"""
Gezellig Dynamics Breach Review - Entry point
"""
import sys
import logging
import json
from urllib import error, request

from app.config import LOCAL_LLM_BASE_URL, LOCAL_LLM_ENABLED, LOCAL_LLM_MODEL, LOCAL_LLM_PROVIDER
from app.runtime_metadata import CURRENT_BUILD_ID, CURRENT_BUILD_LABEL

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


def _check_for_existing_server() -> None:
    build_info_url = "http://127.0.0.1:8000/api/build-info"
    request_object = request.Request(build_info_url, headers={"Accept": "application/json"})

    try:
        with request.urlopen(request_object, timeout=0.6) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        raise SystemExit(
            f"Port 8000 is already serving HTTP, but {build_info_url} returned {exc.code}. "
            "Stop the existing process before starting a new analyzer instance."
        ) from exc
    except error.URLError:
        return

    running_label = str(payload.get("build_label", "unknown"))
    running_id = str(payload.get("build_id", ""))
    if running_id and running_id != CURRENT_BUILD_ID:
        raise SystemExit(
            "A different analyzer build is already serving http://127.0.0.1:8000.\n"
            f"Running build: {running_label}\n"
            f"Current source build: {CURRENT_BUILD_LABEL}\n"
            "Stop the stale server and restart so the web UI does not serve outdated report logic."
        )

    raise SystemExit(
        "The analyzer is already running on http://127.0.0.1:8000 "
        f"with build {running_label or CURRENT_BUILD_LABEL}. Stop it before starting another copy."
    )

if __name__ == "__main__":
    import uvicorn
    _check_for_existing_server()
    llm_status = "ENABLED" if LOCAL_LLM_ENABLED else "DISABLED"

    print("""
    ╔════════════════════════════════════════════════════════════════╗
    ║            GEZELLIG DYNAMICS BREACH REVIEW                    ║
    ║                                                                ║
    ║  Gezellig Dynamics platform for reviewing leaked email        ║
    ║  evidence and identifying exposed personal information.       ║
    ║                                                                ║
    ║  URL: http://127.0.0.1:8000                                   ║
    ║                                                                ║
    ║  ⚠️  SECURITY NOTE: This tool binds to 127.0.0.1 only.       ║
    ║     Do not expose to untrusted networks.                      ║
    ║                                                                ║
    ║  Build: """ + CURRENT_BUILD_LABEL.ljust(56) + """║
    ║                                                                ║
    ║  Local LLM Attribution: """ + llm_status.ljust(36) + """║
    ║  Model: """ + f"{LOCAL_LLM_PROVIDER}/{LOCAL_LLM_MODEL}".ljust(53) + """║
    ║  Endpoint: """ + LOCAL_LLM_BASE_URL.ljust(50) + """║
    ║                                                                ║
    ║  Ctrl+C to stop                                               ║
    ╚════════════════════════════════════════════════════════════════╝
    """)

    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
        log_level="info",
    )
