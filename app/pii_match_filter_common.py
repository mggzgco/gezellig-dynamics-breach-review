"""Shared helpers and keyword sets for type-specific PII match filters."""

from __future__ import annotations

import re

from app.pii_keywords import compile_keyword_patterns


def normalize_filter_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


def extract_line_prefix(text: str, start: int) -> str:
    line_start = text.rfind("\n", 0, start)
    if line_start == -1:
        line_start = 0
    else:
        line_start += 1
    return text[line_start:start]


def extract_local_window(text: str, start: int, end: int, padding: int = 48) -> str:
    window_start = max(0, start - padding)
    window_end = min(len(text), end + padding)
    return text[window_start:window_end]


def has_keyword_match(patterns: list[re.Pattern], text: str) -> bool:
    return any(pattern.search(text) for pattern in patterns)


def last_field_label(prefix_text: str) -> str:
    labels = re.findall(r"([A-Za-z][A-Za-z /'&()\-]{1,40})\s*:\s*", prefix_text, re.IGNORECASE)
    return labels[-1].strip().lower() if labels else ""


LIKELY_NAME_RE = re.compile(r"\b[A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+){1,2}\b")

PERSON_RECORD_PATTERNS = compile_keyword_patterns(
    [
        "patient",
        "member",
        "employee",
        "customer",
        "client",
        "subscriber",
        "insured",
        "dependent",
        "child",
        "student",
        "borrower",
        "applicant",
        "claimant",
        "spouse",
        "resident",
        "guarantor",
        "address",
        "phone",
        "email",
        "mrn",
        "medical record",
        "member id",
        "patient id",
        "subscriber id",
    ]
)
DOB_RECORD_PATTERNS = compile_keyword_patterns(
    [
        "patient",
        "member id",
        "patient id",
        "subscriber id",
        "insured",
        "dependent",
        "child",
        "spouse",
        "guarantor",
        "address",
        "mrn",
        "medical record",
    ]
)
DOB_EXPLICIT_PATTERNS = compile_keyword_patterns(
    ["dob", "date of birth", "birth date", "birthdate", "born", "d.o.b"]
)
DOB_NEGATIVE_PATTERNS = compile_keyword_patterns(
    [
        "deadline",
        "due",
        "appointment",
        "meeting",
        "hearing",
        "scheduled",
        "schedule",
        "renewal",
        "effective",
        "expires",
        "expiration",
        "install",
        "installation",
        "delivery",
        "service date",
        "service dates",
        "adoption date",
        "admission",
        "discharge",
        "court date",
        "start date",
        "termination date",
        "incident date",
        "outage date",
        "marriage date",
        "divorce date",
        "issued",
        "issue date",
        "payment",
        "balance",
        "billing",
        "statement date",
        "training",
        "inspection",
        "audit",
        "launch",
        "maintenance",
        "arrival",
        "arriving",
        "departure",
        "pick-up",
        "drop-off",
    ]
)
EMAIL_LABEL_PATTERNS = compile_keyword_patterns(["email", "e-mail", "email address"])
EMAIL_PERSON_PATTERNS = compile_keyword_patterns(
    ["patient email", "employee email", "member email", "customer email", "personal email"]
)
EMAIL_SERVICE_PATTERNS = compile_keyword_patterns(
    [
        "support",
        "helpdesk",
        "service desk",
        "questions",
        "customer care",
        "account management",
        "property management",
        "quality assurance",
        "human resources",
        "facilities",
        "licensing",
        "coordinator",
        "assigned coordinator",
        "inbox",
    ]
)
PHONE_LABEL_PATTERNS = compile_keyword_patterns(["phone", "phone number", "telephone", "tel", "mobile", "cell"])
PHONE_NEGATIVE_PATTERNS = compile_keyword_patterns(
    [
        "contact",
        "call",
        "support",
        "helpdesk",
        "service desk",
        "customer care",
        "questions",
        "balance inquiry",
        "recall",
        "administrator",
        "department",
        "office",
    ]
)
BANK_POSITIVE_PATTERNS = compile_keyword_patterns(
    ["bank account", "checking", "savings", "direct deposit", "ach", "routing", "wire", "deposit account"]
)
BANK_NEGATIVE_PATTERNS = compile_keyword_patterns(
    [
        "loan",
        "gift card",
        "claim",
        "policy",
        "invoice",
        "order",
        "payment due",
        "balance",
        "statement",
        "membership",
        "member",
        "customer care",
        "suspended",
        "autopay",
    ]
)
SSN_LABEL_PATTERNS = compile_keyword_patterns(["ssn", "social security", "social security number"])
SSN_NEGATIVE_PATTERNS = compile_keyword_patterns(["ndc", "drug", "medication", "prescription", "rx"])
IP_LABEL_PATTERNS = compile_keyword_patterns(["ip", "ip address", "source ip", "client ip", "origin ip"])
IP_PERSON_PATTERNS = compile_keyword_patterns(
    ["login", "sign in", "sign-in", "session", "device", "portal", "browser", "user agent"]
)
IP_NEGATIVE_PATTERNS = compile_keyword_patterns(
    [
        "intrusion",
        "firewall",
        "server",
        "port",
        "ssh",
        "failed login",
        "cpu",
        "monitoring",
        "web-server",
        "alert",
        "network team",
        "operations",
        "ticket",
    ]
)
GENERIC_EMAIL_LOCALS = {
    "admin",
    "audit",
    "alert",
    "alerts",
    "billing",
    "benefits",
    "compliance",
    "contact",
    "contracts",
    "customercare",
    "dpo",
    "facilities",
    "help",
    "helpdesk",
    "intake",
    "inbox",
    "info",
    "it",
    "legal",
    "licensing",
    "marketing",
    "noreply",
    "no-reply",
    "office",
    "ops",
    "operations",
    "privacy",
    "recall",
    "sales",
    "security",
    "service",
    "support",
    "team",
}
PUBLIC_WEBMAIL_DOMAINS = {
    "aol.com",
    "gmail.com",
    "hotmail.com",
    "icloud.com",
    "live.com",
    "msn.com",
    "outlook.com",
    "protonmail.com",
    "yahoo.com",
}
EMAIL_HEADER_LABELS = {"from", "to", "cc", "bcc", "reply to", "reply-to", "sender"}
