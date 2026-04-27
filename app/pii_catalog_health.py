"""Healthcare and clinical detection rules."""

from __future__ import annotations

import re

from app.pii_normalization import compact_alnum, digits_only
from app.pii_pattern_types import PIIPattern
from app.pii_validation import mrn_check, npi_check
from app.settings import CONTEXT_WINDOW_CHARS, REGEX_FLAGS

MEDICARE_PATTERN = PIIPattern(
    name="MEDICARE",
    category="health_identifier",
    subtype="medicare_beneficiary_identifier",
    patterns=[
        re.compile(
            r"\b[1-9][AC-HJ-NP-RT-Y]{2}[0-9][AC-HJ-NP-RT-Y]{2}[0-9][AC-HJ-NP-RT-Y]{2}[0-9]{2}\b",
            REGEX_FLAGS,
        )
    ],
    risk_level="HIGH",
    requires_context=False,
    context_keywords=["medicare", "mbi"],
    strong_context_keywords=["medicare", "medicare number", "mbi"],
    context_window=CONTEXT_WINDOW_CHARS,
    hipaa=True,
    ccpa=False,
    pipeda=False,
    notification_required=True,
    normalizer=compact_alnum,
    base_confidence=0.96,
    min_confidence=0.92,
    detection_method="regex+structure",
    priority=93,
)

MRN_PATTERN = PIIPattern(
    name="MRN",
    category="health_identifier",
    subtype="medical_record_number",
    patterns=[
        re.compile(
            r"\b(?:MRN|MED(?:ICAL)?[_\s]+REC(?:ORD)?(?:[_\s]+NUMBER)?|RECORD[_\s]+NUMBER)[#\s:.,-]*([A-Z0-9]{4,12})\b",
            REGEX_FLAGS,
        )
    ],
    risk_level="HIGH",
    requires_context=False,
    context_keywords=["mrn", "medical record", "record number"],
    strong_context_keywords=["mrn", "medical record number"],
    context_window=150,
    hipaa=True,
    ccpa=False,
    pipeda=False,
    notification_required=True,
    validator=mrn_check,
    normalizer=compact_alnum,
    match_group=1,
    base_confidence=0.88,
    min_confidence=0.84,
    detection_method="regex+label",
    priority=92,
)

NPI_PATTERN = PIIPattern(
    name="NPI",
    category="professional_identifier",
    subtype="national_provider_identifier",
    patterns=[
        re.compile(
            r"\b(?:npi|national\s+provider(?:\s+(?:identifier|id|number))?)[\s#:.,-]*([0-9]{10})\b",
            REGEX_FLAGS,
        )
    ],
    risk_level="MEDIUM",
    requires_context=False,
    context_keywords=["npi", "provider identifier", "provider id"],
    strong_context_keywords=["npi", "national provider identifier"],
    context_window=150,
    hipaa=True,
    ccpa=False,
    pipeda=False,
    notification_required=False,
    validator=npi_check,
    normalizer=digits_only,
    match_group=1,
    base_confidence=0.86,
    min_confidence=0.84,
    detection_method="regex+label+checksum",
    priority=91,
)

ICD10_PATTERN = PIIPattern(
    name="ICD10",
    category="health_information",
    subtype="diagnosis_code",
    patterns=[re.compile(r"\b[A-Z][0-9]{2}(?:\.[0-9A-Z]{1,4})?\b", REGEX_FLAGS)],
    risk_level="MEDIUM",
    requires_context=True,
    context_keywords=["diagnosis", "icd", "dx", "condition", "diagnostic"],
    strong_context_keywords=["icd", "icd-10", "diagnosis"],
    context_window=CONTEXT_WINDOW_CHARS,
    hipaa=True,
    ccpa=False,
    pipeda=False,
    notification_required=False,
    normalizer=compact_alnum,
    base_confidence=0.74,
    min_confidence=0.78,
    detection_method="regex+context",
    priority=81,
)

NDC_PATTERN = PIIPattern(
    name="NDC",
    category="health_information",
    subtype="drug_code",
    patterns=[re.compile(r"\b(?:\d{5}-\d{4}-\d{2}|\d{5}-\d{3}-\d{2}|\d{4}-\d{4}-\d{2})\b", REGEX_FLAGS)],
    risk_level="MEDIUM",
    requires_context=True,
    context_keywords=["ndc", "drug", "medication", "prescription", "pharmaceutical", "rx"],
    strong_context_keywords=["ndc", "drug code", "prescription"],
    context_window=CONTEXT_WINDOW_CHARS,
    hipaa=True,
    ccpa=False,
    pipeda=False,
    notification_required=False,
    normalizer=digits_only,
    base_confidence=0.74,
    min_confidence=0.78,
    detection_method="regex+context",
    priority=80,
)

HEALTH_PATTERNS = (
    MEDICARE_PATTERN,
    MRN_PATTERN,
    NPI_PATTERN,
    ICD10_PATTERN,
    NDC_PATTERN,
)
