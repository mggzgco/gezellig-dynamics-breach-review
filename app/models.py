from __future__ import annotations

from dataclasses import dataclass, field
from dataclasses import asdict
from datetime import datetime
from typing import Optional
from enum import Enum
import uuid

class RiskLevel(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    NONE = "NONE"


@dataclass
class PIIMatch:
    """Single PII finding"""
    pii_type: str
    pii_category: str
    pii_subtype: str
    risk_level: str
    redacted_value: str
    excerpt: str
    source_ref: str  # filename or attachment name
    char_offset: int
    confidence: float
    detection_method: str
    hipaa: bool
    ccpa: bool
    pipeda: bool
    notification_required: bool
    normalized_value: str = ""
    evidence: list[str] = field(default_factory=list)


@dataclass
class Attachment:
    """Email attachment representation"""
    filename: str
    mime_type: str
    data: bytes
    source_eml: str


@dataclass
class AttachmentProcessingRecord:
    """Stable attachment-processing metadata used across QA, reporting, and jobs."""

    filename: str
    mime_type: str
    extraction_method: str = ""
    structured: bool = False
    page_count: int = 0
    table_count: int = 0
    ocr_used: bool = False
    ocr_page_count: int = 0
    ocr_avg_confidence: float = 0.0
    low_confidence_ocr: bool = False
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialize attachment processing metadata for JSON/report output."""
        return asdict(self)


@dataclass
class EmailAnalysisResult:
    """Result of analyzing a single .eml file"""
    eml_filename: str
    from_address: Optional[str]
    to_addresses: list[str]
    cc_addresses: list[str]
    bcc_addresses: list[str]
    subject: str
    from_name: Optional[str] = None
    to_names: list[str] = field(default_factory=list)
    pii_matches: list[PIIMatch] = field(default_factory=list)
    source_texts: dict[str, str] = field(default_factory=dict)
    source_extractions: dict[str, "SourceExtractionMetadata"] = field(default_factory=dict)
    attachments_processed: list[AttachmentProcessingRecord] = field(default_factory=list)
    qa_review: Optional["FileQAReview"] = None
    error: Optional[str] = None


@dataclass
class SourceExtractionMetadata:
    """Structured metadata describing how one source text was extracted."""

    source_ref: str = ""
    extraction_method: str = "plain_text"
    parser: str = ""
    page_count: int = 0
    table_count: int = 0
    structured: bool = False
    ocr_used: bool = False
    ocr_page_count: int = 0
    ocr_avg_confidence: float = 0.0
    low_confidence_ocr: bool = False
    warnings: list[str] = field(default_factory=list)


@dataclass
class FileQAReview:
    """File-level QA review output for human escalation decisions."""
    reviewed: bool = False
    used_model: bool = False
    status: str = "not_run"  # not_run | clear | needs_review | error
    needs_human_review: bool = False
    confidence: float = 0.0
    suspected_missing_types: list[str] = field(default_factory=list)
    questionable_detected_types: list[str] = field(default_factory=list)
    evidence_quotes: list[str] = field(default_factory=list)
    reason: str = ""
    model: Optional[str] = None
    error: Optional[str] = None
    followup_scanned: bool = False
    followup_match_count: int = 0
    followup_pii_types: list[str] = field(default_factory=list)
    followup_source_refs: list[str] = field(default_factory=list)


@dataclass
class PersonRecord:
    """Aggregated record of a person with exposed PII"""
    person_id: str
    canonical_email: Optional[str]
    canonical_name: Optional[str]
    entity_type: str = "PERSON"
    attribution_confidence: float = 0.0
    attribution_methods: list[str] = field(default_factory=list)
    attribution_evidence: list[str] = field(default_factory=list)
    all_emails: set[str] = field(default_factory=set)
    all_names: set[str] = field(default_factory=set)
    pii_matches: list[PIIMatch] = field(default_factory=list)
    source_emails: list[str] = field(default_factory=list)
    risk_score: float = 0.0
    highest_risk_level: str = "NONE"
    notification_required: bool = False
    regulations_triggered: dict[str, bool] = field(default_factory=lambda: {"HIPAA": False, "CCPA": False, "PIPEDA": False})

    def __post_init__(self):
        if not self.person_id:
            self.person_id = str(uuid.uuid4())


@dataclass
class AnalysisJobSummary:
    """Stable typed summary returned by the end-to-end analysis pipeline."""

    job_id: str
    total_files_processed: int
    total_persons_affected: int
    persons_high_risk: int
    persons_medium_risk: int
    persons_notification_required: int
    persons: list[PersonRecord] = field(default_factory=list)
    html_report: str = ""
    html_content: str = ""
    csv_report: str = ""
    file_review_csv: str = ""
    file_review_expected: bool = False
    file_review_available: bool = False
    build_id: str = ""
    build_label: str = ""
    html_report_schema_version: str = ""
    csv_report_schema_version: str = ""
    file_review_schema_version: str = ""
    files_ai_reviewed: int = 0
    files_needing_human_review: int = 0
    files_with_followup_matches: int = 0
    files_with_low_confidence_ocr: int = 0

    def to_dict(self) -> dict:
        """Serialize the summary for JSON responses or debugging output."""
        return {
            "job_id": self.job_id,
            "total_files_processed": self.total_files_processed,
            "total_persons_affected": self.total_persons_affected,
            "persons_high_risk": self.persons_high_risk,
            "persons_medium_risk": self.persons_medium_risk,
            "persons_notification_required": self.persons_notification_required,
            "persons": [
                {
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
                }
                for person in self.persons
            ],
            "html_report": self.html_report,
            "html_content": self.html_content,
            "csv_report": self.csv_report,
            "file_review_csv": self.file_review_csv,
            "file_review_expected": self.file_review_expected,
            "file_review_available": self.file_review_available,
            "build_id": self.build_id,
            "build_label": self.build_label,
            "html_report_schema_version": self.html_report_schema_version,
            "csv_report_schema_version": self.csv_report_schema_version,
            "file_review_schema_version": self.file_review_schema_version,
            "files_ai_reviewed": self.files_ai_reviewed,
            "files_needing_human_review": self.files_needing_human_review,
            "files_with_followup_matches": self.files_with_followup_matches,
            "files_with_low_confidence_ocr": self.files_with_low_confidence_ocr,
        }


@dataclass
class ProgressUpdate:
    """Progress event for SSE"""
    status: str  # "progress" | "complete" | "error"
    processed: int = 0
    total: int = 0
    current_file: str = ""
    persons_found: int = 0
    message: str = ""


class JobStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETE = "complete"
    ERROR = "error"


@dataclass
class JobState:
    """In-memory job state"""
    job_id: str
    status: JobStatus
    progress: ProgressUpdate
    result_summary: Optional[AnalysisJobSummary] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
