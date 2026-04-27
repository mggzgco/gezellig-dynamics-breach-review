"""Shared setup-runtime models, constants, and timestamp helpers."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


OLLAMA_DOWNLOAD_URL_PLACEHOLDER = "__OLLAMA_DOWNLOAD_URL__"
OLLAMA_INSTALL_COMMAND_PLACEHOLDER = "__OLLAMA_INSTALL_COMMAND__"
TESSERACT_INSTALL_COMMAND_PLACEHOLDER = "__TESSERACT_INSTALL_COMMAND__"
DEPENDENCY_OLLAMA = "ollama"
DEPENDENCY_OCR = "ocr"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def isoformat_or_none(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None


@dataclass
class SetupCheck:
    label: str
    ok: bool
    detail: str


@dataclass
class InstallSpec:
    dependency: str
    label: str
    command: list[str]
    display_command: str


@dataclass
class SetupTaskState:
    status: str = "idle"
    kind: str = "none"
    subject: str = ""
    detail: str = "No background setup activity."
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    log_tail: deque[str] = field(default_factory=lambda: deque(maxlen=14))

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "kind": self.kind,
            "subject": self.subject,
            "detail": self.detail,
            "started_at": isoformat_or_none(self.started_at),
            "completed_at": isoformat_or_none(self.completed_at),
            "log_tail": list(self.log_tail),
        }


@dataclass
class StructuredCheckState:
    ok: bool
    detail: str
    checked_at: Optional[datetime] = None
