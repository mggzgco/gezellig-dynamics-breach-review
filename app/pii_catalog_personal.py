"""Personal, contact, location, and online identifier detection rules."""

from __future__ import annotations

import re

from app.pii_match_filter_personal import dob_match_filter, email_match_filter, ipv4_match_filter, phone_match_filter
from app.pii_normalization import (
    compact_alnum,
    digits_only,
    normalize_address,
    normalize_email,
    normalize_name,
    normalize_phone,
)
from app.pii_pattern_types import PIIPattern
from app.pii_validation import dob_check, full_name_check, normalize_dob
from app.settings import CONTEXT_WINDOW_CHARS, REGEX_FLAGS

EMAIL_PATTERN = PIIPattern(
    name="EMAIL",
    category="contact",
    subtype="email_address",
    patterns=[
        re.compile(
            r"\b[A-Za-z0-9](?:[A-Za-z0-9._%+\-]{0,62}[A-Za-z0-9])?@(?:[A-Za-z0-9](?:[A-Za-z0-9\-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,24}\b",
            REGEX_FLAGS,
        )
    ],
    risk_level="MEDIUM",
    requires_context=False,
    context_keywords=["email", "e-mail", "mail", "contact"],
    strong_context_keywords=["email", "email address", "e-mail"],
    context_window=CONTEXT_WINDOW_CHARS,
    hipaa=True,
    ccpa=True,
    pipeda=True,
    notification_required=False,
    normalizer=normalize_email,
    match_filter=email_match_filter,
    base_confidence=0.98,
    min_confidence=0.95,
    detection_method="regex",
    priority=88,
)

PHONE_PATTERN = PIIPattern(
    name="PHONE",
    category="contact",
    subtype="phone_number",
    patterns=[
        re.compile(
            r"(?<!\w)(?:\+?1[-.\s]?)?(?:\([2-9][0-9]{2}\)|[2-9][0-9]{2})[-.\s]?[2-9][0-9]{2}[-.\s]?[0-9]{4}(?:\s*(?:x|ext\.?)\s*[0-9]{1,6})?(?!\w)",
            REGEX_FLAGS,
        )
    ],
    risk_level="MEDIUM",
    requires_context=True,
    context_keywords=["phone", "tel", "telephone", "mobile", "cell", "fax", "call", "contact"],
    strong_context_keywords=["phone", "phone number", "telephone", "mobile", "cell"],
    negative_keywords=["contact", "call", "support", "helpdesk", "service desk", "customer care", "questions"],
    context_window=CONTEXT_WINDOW_CHARS,
    hipaa=True,
    ccpa=True,
    pipeda=True,
    notification_required=False,
    normalizer=normalize_phone,
    match_filter=phone_match_filter,
    base_confidence=0.66,
    min_confidence=0.7,
    detection_method="regex+context",
    priority=87,
)

DOB_PATTERN = PIIPattern(
    name="DOB",
    category="personal_profile",
    subtype="date_of_birth",
    patterns=[
        re.compile(r"\b(?:19\d{2}|20\d{2})[-/](?:0[1-9]|1[0-2])[-/](?:0[1-9]|[12]\d|3[01])\b", REGEX_FLAGS),
        re.compile(r"\b(?:0[1-9]|1[0-2])[/-](?:0[1-9]|[12]\d|3[01])[/-](?:19\d{2}|20\d{2}|\d{2})\b", REGEX_FLAGS),
        re.compile(
            r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+(?:0?[1-9]|[12]\d|3[01]),?\s+(?:19\d{2}|20\d{2})\b",
            REGEX_FLAGS,
        ),
        re.compile(
            r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\s+(?:0?[1-9]|[12]\d|3[01]),?\s+(?:19\d{2}|20\d{2})\b",
            REGEX_FLAGS,
        ),
        re.compile(
            r"\b(?:0?[1-9]|[12]\d|3[01])\s+(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\s+(?:19\d{2}|20\d{2})\b",
            REGEX_FLAGS,
        ),
    ],
    risk_level="MEDIUM",
    requires_context=False,
    context_keywords=["dob", "date of birth", "birth date", "birthdate", "birthday", "born"],
    strong_context_keywords=["dob", "date of birth", "birthdate"],
    negative_keywords=[
        "deadline",
        "due",
        "appointment",
        "meeting",
        "hearing",
        "scheduled",
        "renewal",
        "effective",
        "expires",
        "expiration",
        "service date",
        "service dates",
        "adoption date",
        "training",
        "inspection",
        "audit",
    ],
    context_window=CONTEXT_WINDOW_CHARS,
    hipaa=True,
    ccpa=True,
    pipeda=True,
    notification_required=False,
    validator=dob_check,
    match_filter=dob_match_filter,
    normalizer=normalize_dob,
    base_confidence=0.72,
    min_confidence=0.72,
    detection_method="regex+validation",
    priority=86,
)

FULL_NAME_PATTERN = PIIPattern(
    name="FULL_NAME",
    category="identity",
    subtype="full_name",
    patterns=[
        re.compile(
            r"\b(?:full\s+name|name|record\s+owner|patient\s+name|employee\s+name|member\s+name|student\s+name|borrower\s+name|applicant\s+name|customer\s+name|client\s+name|insured\s+name|subscriber\s+name|dependent\s+name|guarantor\s+name)\b\s*[:#,\-]\s*([A-Z][A-Za-z'.-]+(?: [A-Z][A-Za-z'.-]+){1,3})\b",
            REGEX_FLAGS,
        ),
        re.compile(
            r"\b(?:patient|employee|member|student|borrower|applicant|customer|client|insured|subscriber|dependent|guarantor|spouse|child|parent)\b\s*[:#-]\s*([A-Z][A-Za-z'.-]+(?: [A-Z][A-Za-z'.-]+){1,3})\b",
            REGEX_FLAGS,
        ),
    ],
    risk_level="LOW",
    requires_context=False,
    context_keywords=["name", "patient", "employee", "member", "student"],
    strong_context_keywords=["full name", "name", "patient", "employee", "member"],
    context_window=CONTEXT_WINDOW_CHARS,
    hipaa=True,
    ccpa=True,
    pipeda=True,
    notification_required=False,
    validator=full_name_check,
    normalizer=normalize_name,
    match_group=1,
    base_confidence=0.83,
    min_confidence=0.82,
    detection_method="regex+label",
    priority=85,
)

ADDRESS_PATTERN = PIIPattern(
    name="ADDRESS",
    category="location",
    subtype="street_address",
    patterns=[
        re.compile(
            r"\b\d{1,6}\s+(?:[A-Za-z0-9.'#-]+\s+){1,6}(?:St|Street|Ave|Avenue|Blvd|Boulevard|Dr|Drive|Rd|Road|Ln|Lane|Way|Ct|Court|Pl|Place|Terr|Terrace|Pkwy|Parkway|Cir|Circle|Hwy|Highway)\b(?:,?\s*(?:Apt|Apartment|Unit|Suite|Ste|#)\s*[A-Za-z0-9-]+)?(?:,?\s*[A-Za-z .'-]+,\s*[A-Z]{2}\s+\d{5}(?:-\d{4})?)?",
            REGEX_FLAGS,
        )
    ],
    risk_level="MEDIUM",
    requires_context=False,
    context_keywords=["address", "street", "mailing", "home", "residence"],
    strong_context_keywords=["address", "mailing address", "home address"],
    context_window=CONTEXT_WINDOW_CHARS,
    hipaa=True,
    ccpa=True,
    pipeda=True,
    notification_required=False,
    normalizer=normalize_address,
    base_confidence=0.8,
    min_confidence=0.78,
    detection_method="regex+structure",
    priority=84,
)

ZIP_PATTERN = PIIPattern(
    name="ZIP",
    category="location",
    subtype="postal_code",
    patterns=[
        re.compile(r"\b\d{5}(?:-\d{4})?\b", REGEX_FLAGS),
        re.compile(r"\b[A-Z]\d[A-Z]\s?\d[A-Z]\d\b", REGEX_FLAGS),
    ],
    risk_level="MEDIUM",
    requires_context=True,
    context_keywords=["zip", "zipcode", "postal", "postal code", "postcode"],
    strong_context_keywords=["zip", "zip code", "postal code"],
    context_window=CONTEXT_WINDOW_CHARS,
    hipaa=True,
    ccpa=True,
    pipeda=True,
    notification_required=False,
    normalizer=compact_alnum,
    base_confidence=0.54,
    min_confidence=0.72,
    detection_method="regex+context",
    priority=83,
)

VIN_PATTERN = PIIPattern(
    name="VIN",
    category="vehicle_identifier",
    subtype="vehicle_identification_number",
    patterns=[re.compile(r"\b[A-HJ-NPR-Z0-9]{17}\b", REGEX_FLAGS)],
    risk_level="MEDIUM",
    requires_context=True,
    context_keywords=["vin", "vehicle", "auto", "car", "vehicle id"],
    strong_context_keywords=["vin", "vehicle identification number"],
    context_window=CONTEXT_WINDOW_CHARS,
    hipaa=False,
    ccpa=True,
    pipeda=True,
    notification_required=False,
    normalizer=compact_alnum,
    base_confidence=0.78,
    min_confidence=0.8,
    detection_method="regex+context",
    priority=82,
)

IPV4_PATTERN = PIIPattern(
    name="IPV4",
    category="online_identifier",
    subtype="ipv4_address",
    patterns=[
        re.compile(
            r"\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9]{1,2})\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9]{1,2})\b",
            REGEX_FLAGS,
        )
    ],
    risk_level="LOW",
    requires_context=True,
    context_keywords=["ip", "ip address", "login", "device"],
    strong_context_keywords=["ip", "ip address"],
    negative_keywords=["intrusion", "firewall", "server", "port", "ssh", "failed login", "cpu", "monitoring"],
    context_window=CONTEXT_WINDOW_CHARS,
    hipaa=False,
    ccpa=True,
    pipeda=True,
    notification_required=False,
    normalizer=digits_only,
    match_filter=ipv4_match_filter,
    base_confidence=0.92,
    min_confidence=0.9,
    detection_method="regex+context",
    priority=79,
)

PERSONAL_PATTERNS = (
    DOB_PATTERN,
    ADDRESS_PATTERN,
    FULL_NAME_PATTERN,
    ZIP_PATTERN,
    EMAIL_PATTERN,
    PHONE_PATTERN,
    VIN_PATTERN,
    IPV4_PATTERN,
)
