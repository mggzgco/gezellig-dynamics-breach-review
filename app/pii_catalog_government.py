"""Government and public-sector identifier detection rules."""

from __future__ import annotations

import re

from app.pii_match_filter_sensitive import ssn_match_filter
from app.pii_normalization import compact_alnum, digits_only
from app.pii_pattern_types import PIIPattern
from app.pii_validation import drivers_license_check, passport_check, sin_check
from app.settings import CONTEXT_WINDOW_CHARS, REGEX_FLAGS

SSN_PATTERN = PIIPattern(
    name="SSN",
    category="government_identifier",
    subtype="social_security_number",
    patterns=[
        re.compile(
            r"\b(?!000|666|9\d{2})([0-6]\d{2}|[789][0-1]\d)[-\s]?(?!00)\d{2}[-\s]?(?!0000)\d{4}\b",
            REGEX_FLAGS,
        )
    ],
    risk_level="HIGH",
    requires_context=False,
    context_keywords=["ssn", "social security", "social security number"],
    strong_context_keywords=["ssn", "social security number"],
    context_window=CONTEXT_WINDOW_CHARS,
    hipaa=True,
    ccpa=True,
    pipeda=False,
    notification_required=True,
    normalizer=digits_only,
    match_filter=ssn_match_filter,
    base_confidence=0.97,
    min_confidence=0.95,
    detection_method="regex+structure",
    priority=100,
)

SIN_PATTERN = PIIPattern(
    name="SIN",
    category="government_identifier",
    subtype="social_insurance_number",
    patterns=[re.compile(r"\b[1-9]\d{2}[-\s]?\d{3}[-\s]?\d{3}\b", REGEX_FLAGS)],
    risk_level="HIGH",
    requires_context=True,
    context_keywords=[
        "sin",
        "social insurance",
        "social insurance number",
        "insurance number",
        "numéro d'assurance sociale",
    ],
    strong_context_keywords=["sin", "social insurance number"],
    context_window=CONTEXT_WINDOW_CHARS,
    hipaa=False,
    ccpa=False,
    pipeda=True,
    notification_required=True,
    validator=sin_check,
    normalizer=digits_only,
    base_confidence=0.82,
    min_confidence=0.82,
    detection_method="regex+checksum",
    priority=99,
)

PASSPORT_PATTERN = PIIPattern(
    name="PASSPORT",
    category="government_identifier",
    subtype="passport_number",
    patterns=[
        re.compile(
            r"\b(?:passport|passeport)(?:\s+(?:number|no\.?|#))?[\s#:.,-]*([A-Z0-9][A-Z0-9 -]{5,15})\b",
            REGEX_FLAGS,
        )
    ],
    risk_level="HIGH",
    requires_context=False,
    context_keywords=["passport", "travel document", "passeport"],
    strong_context_keywords=["passport", "passport number", "passport no"],
    context_window=150,
    hipaa=False,
    ccpa=True,
    pipeda=True,
    notification_required=True,
    validator=passport_check,
    normalizer=compact_alnum,
    match_group=1,
    base_confidence=0.87,
    min_confidence=0.84,
    detection_method="regex+label",
    priority=95,
)

DRIVERS_LICENSE_PATTERN = PIIPattern(
    name="DRIVERS_LICENSE",
    category="government_identifier",
    subtype="drivers_license_number",
    patterns=[
        re.compile(
            r"\b(?:driver'?s?[_\s]+licen[sc]e|drivers?[_\s]+licen[sc]e|driving[_\s]+licen[sc]e)(?:[_\s]+(?:number|no\.?|#))?[\s#:.,-]*([A-Z0-9][A-Z0-9 -]{4,24})\b",
            REGEX_FLAGS,
        )
    ],
    risk_level="HIGH",
    requires_context=False,
    context_keywords=["driver's license", "drivers license", "driving licence", "driving license"],
    strong_context_keywords=["driver's license", "drivers license", "driver license number"],
    context_window=200,
    hipaa=False,
    ccpa=True,
    pipeda=True,
    notification_required=True,
    validator=drivers_license_check,
    normalizer=compact_alnum,
    match_group=1,
    base_confidence=0.84,
    min_confidence=0.82,
    detection_method="regex+label",
    priority=94,
)

EIN_PATTERN = PIIPattern(
    name="EIN",
    category="government_identifier",
    subtype="employer_identification_number",
    patterns=[
        re.compile(
            r"\b(?:ein|fein|employer\s+identification(?:\s+number)?|federal\s+tax(?:\s+id(?:entification)?(?:\s+number)?)?)[\s#:.,-]*((?:0[1-9]|[1-9]\d)[- ]?\d{7})\b",
            REGEX_FLAGS,
        )
    ],
    risk_level="LOW",
    requires_context=False,
    context_keywords=["ein", "fein", "employer identification", "federal tax"],
    strong_context_keywords=["ein", "employer identification number", "federal tax id"],
    context_window=CONTEXT_WINDOW_CHARS,
    hipaa=False,
    ccpa=True,
    pipeda=False,
    notification_required=False,
    normalizer=digits_only,
    match_group=1,
    base_confidence=0.8,
    min_confidence=0.78,
    detection_method="regex+label",
    priority=89,
)

GOVERNMENT_IDENTIFIER_PATTERNS = (
    SSN_PATTERN,
    SIN_PATTERN,
    PASSPORT_PATTERN,
    DRIVERS_LICENSE_PATTERN,
    EIN_PATTERN,
)
