"""Runtime settings and environment-driven toggles.

This module owns operational configuration only. Detection rules and PII
catalog definitions live elsewhere.
"""

from __future__ import annotations

import os
import re
from pathlib import Path


UPLOAD_DIR = Path("jobs")
MAX_FILE_SIZE_MB = 2048
THREAD_POOL_WORKERS = 4
CONTEXT_WINDOW_CHARS = 100
MAX_ATTACHMENT_SIZE_MB = 50
JOB_EXPIRY_HOURS = 24
ZIP_MAX_RECURSION_DEPTH = 3


def _read_env_file(env_path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not env_path.exists():
        return values

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        values[key] = value.strip().strip('"').strip("'")
    return values


_LOCAL_ENV_DISABLED = os.environ.get("PII_DISABLE_LOCAL_ENV", "").strip().lower() in {"1", "true", "yes", "on"}
_ENV_FILE_VALUES = {} if _LOCAL_ENV_DISABLED else _read_env_file(Path(__file__).resolve().parent.parent / ".env.local")


def _env_value(name: str) -> str | None:
    if name in os.environ:
        return os.environ[name]
    return _ENV_FILE_VALUES.get(name)


def _env_flag(name: str, default: bool) -> bool:
    value = _env_value(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = _env_value(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    value = _env_value(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


MAX_CONCURRENT_JOBS = max(1, _env_int("PII_MAX_CONCURRENT_JOBS", 2))
LOCAL_LLM_ENABLED = _env_flag("PII_LOCAL_LLM_ENABLED", False)
LOCAL_LLM_PROVIDER = (_env_value("PII_LOCAL_LLM_PROVIDER") or "ollama").strip().lower()
LOCAL_LLM_MODEL = (_env_value("PII_LOCAL_LLM_MODEL") or "qwen3:4b").strip()
LOCAL_LLM_BASE_URL = (_env_value("PII_LOCAL_LLM_BASE_URL") or "http://127.0.0.1:11434").strip().rstrip("/")
LOCAL_LLM_TIMEOUT_SECONDS = _env_float("PII_LOCAL_LLM_TIMEOUT_SECONDS", 30.0)
LOCAL_LLM_MAX_CONTEXT_CHARS = _env_int("PII_LOCAL_LLM_MAX_CONTEXT_CHARS", 1600)
LOCAL_LLM_MAX_CANDIDATES = _env_int("PII_LOCAL_LLM_MAX_CANDIDATES", 6)
LOCAL_LLM_MAX_REQUESTS_PER_EMAIL = _env_int("PII_LOCAL_LLM_MAX_REQUESTS_PER_EMAIL", 6)
LOCAL_LLM_TRIGGER_CONFIDENCE = _env_float("PII_LOCAL_LLM_TRIGGER_CONFIDENCE", 0.86)
LOCAL_LLM_ACCEPT_CONFIDENCE = _env_float("PII_LOCAL_LLM_ACCEPT_CONFIDENCE", 0.68)
LOCAL_LLM_AMBIGUITY_MARGIN = _env_float("PII_LOCAL_LLM_AMBIGUITY_MARGIN", 0.08)
LOCAL_LLM_FILE_QA_ENABLED = _env_flag("PII_LOCAL_LLM_FILE_QA_ENABLED", LOCAL_LLM_ENABLED)
LOCAL_LLM_FILE_QA_REVIEW_ALL = _env_flag("PII_LOCAL_LLM_FILE_QA_REVIEW_ALL", False)
LOCAL_LLM_FILE_QA_MAX_CONTEXT_CHARS = _env_int("PII_LOCAL_LLM_FILE_QA_MAX_CONTEXT_CHARS", 1000)
LOCAL_LLM_FILE_QA_ACCEPT_CONFIDENCE = _env_float("PII_LOCAL_LLM_FILE_QA_ACCEPT_CONFIDENCE", 0.62)
LOCAL_LLM_FILE_QA_TIMEOUT_SECONDS = _env_float("PII_LOCAL_LLM_FILE_QA_TIMEOUT_SECONDS", max(LOCAL_LLM_TIMEOUT_SECONDS, 45.0))
LOCAL_LLM_FILE_QA_WORKERS = _env_int("PII_LOCAL_LLM_FILE_QA_WORKERS", 1)
LOCAL_LLM_FILE_QA_NUM_PREDICT = _env_int("PII_LOCAL_LLM_FILE_QA_NUM_PREDICT", 112)
LOCAL_LLM_FILE_QA_KEEP_ALIVE = (_env_value("PII_LOCAL_LLM_FILE_QA_KEEP_ALIVE") or "15m").strip()
OCR_LANGUAGES = (_env_value("PII_OCR_LANGUAGES") or "eng+fra").strip()
OCR_LOW_CONFIDENCE_THRESHOLD = _env_float("PII_OCR_LOW_CONFIDENCE_THRESHOLD", 72.0)
OCR_MIN_WORDS = _env_int("PII_OCR_MIN_WORDS", 4)
PDF_PAGE_OCR_TEXT_THRESHOLD = _env_int("PII_PDF_PAGE_OCR_TEXT_THRESHOLD", 40)

REGEX_FLAGS = re.IGNORECASE | re.MULTILINE
