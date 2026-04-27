from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

APP_VERSION = "1.1.0"
BACKEND_RUNTIME_SCHEMA_VERSION = "2026-04-21.1"
HTML_REPORT_SCHEMA_VERSION = "2026-04-21.1"
CSV_REPORT_SCHEMA_VERSION = "2026-04-21.2"
FILE_REVIEW_SCHEMA_VERSION = "2026-04-21.2"

REPO_ROOT = Path(__file__).resolve().parent.parent
BUILD_FINGERPRINT_GLOBS = (
    "run.py",
    "app/**/*.py",
    "app/reporting/templates/**/*.j2",
    "app/static/index.html",
)


def _iter_fingerprint_files() -> list[Path]:
    paths: set[Path] = set()
    for pattern in BUILD_FINGERPRINT_GLOBS:
        paths.update(REPO_ROOT.glob(pattern))
    return sorted(path for path in paths if path.is_file())


def compute_source_build_id() -> str:
    digest = sha256()
    for path in _iter_fingerprint_files():
        relative_path = path.relative_to(REPO_ROOT).as_posix()
        stats = path.stat()
        digest.update(f"{relative_path}|{stats.st_size}|{stats.st_mtime_ns}".encode("utf-8"))
    return digest.hexdigest()[:12]


CURRENT_BUILD_ID = compute_source_build_id()
CURRENT_BUILD_LABEL = f"{APP_VERSION}+{CURRENT_BUILD_ID}"


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def get_runtime_metadata() -> dict[str, str]:
    return {
        "app_version": APP_VERSION,
        "build_id": CURRENT_BUILD_ID,
        "build_label": CURRENT_BUILD_LABEL,
        "backend_runtime_schema_version": BACKEND_RUNTIME_SCHEMA_VERSION,
        "html_report_schema_version": HTML_REPORT_SCHEMA_VERSION,
        "csv_report_schema_version": CSV_REPORT_SCHEMA_VERSION,
        "file_review_schema_version": FILE_REVIEW_SCHEMA_VERSION,
    }
