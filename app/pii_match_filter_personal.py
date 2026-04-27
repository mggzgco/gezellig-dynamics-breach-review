"""Personal/contact-oriented PII match filters."""

from __future__ import annotations

import re

from app.pii_match_filter_common import (
    DOB_EXPLICIT_PATTERNS,
    DOB_NEGATIVE_PATTERNS,
    DOB_RECORD_PATTERNS,
    EMAIL_HEADER_LABELS,
    EMAIL_LABEL_PATTERNS,
    EMAIL_PERSON_PATTERNS,
    EMAIL_SERVICE_PATTERNS,
    GENERIC_EMAIL_LOCALS,
    IP_LABEL_PATTERNS,
    IP_NEGATIVE_PATTERNS,
    IP_PERSON_PATTERNS,
    LIKELY_NAME_RE,
    PERSON_RECORD_PATTERNS,
    PHONE_LABEL_PATTERNS,
    PHONE_NEGATIVE_PATTERNS,
    PUBLIC_WEBMAIL_DOMAINS,
    extract_line_prefix,
    extract_local_window,
    has_keyword_match,
    last_field_label,
    normalize_filter_text,
)


def looks_generic_role_email(email_value: str) -> bool:
    local = email_value.split("@", 1)[0].strip().lower()
    local_core = re.sub(r"[^a-z0-9]+", "", local)
    if local in GENERIC_EMAIL_LOCALS or local_core in GENERIC_EMAIL_LOCALS:
        return True
    generic_tokens = (
        "support",
        "help",
        "billing",
        "contact",
        "info",
        "admin",
        "intake",
        "privacy",
        "benefits",
        "care",
        "ops",
        "alert",
        "notice",
        "service",
        "security",
    )
    return any(local.startswith(prefix) or prefix in local_core for prefix in generic_tokens)


def looks_personal_mailbox(email_value: str) -> bool:
    email_lower = email_value.strip().lower()
    if "@" not in email_lower or looks_generic_role_email(email_lower):
        return False

    local, _, domain = email_lower.partition("@")
    if not local or not domain:
        return False

    alpha_chunks = [chunk for chunk in re.split(r"[._+-]+", local) if chunk.isalpha() and len(chunk) >= 2]
    if len(alpha_chunks) >= 2:
        return True

    if domain in PUBLIC_WEBMAIL_DOMAINS and re.search(r"[._+-]", local):
        return True

    if domain in PUBLIC_WEBMAIL_DOMAINS and re.fullmatch(r"[a-z]{3,}\d{0,4}", local):
        return True

    return False


def dob_match_filter(raw_value: str, text: str, start: int, end: int, line_text: str, context_text: str, source_ref: str) -> bool:
    del raw_value, source_ref
    line_lower = normalize_filter_text(line_text).lower()
    context_lower = normalize_filter_text(context_text).lower()
    local_lower = normalize_filter_text(extract_local_window(text, start, end)).lower()
    line_label = last_field_label(extract_line_prefix(text, start))

    if line_label:
        if has_keyword_match(DOB_EXPLICIT_PATTERNS, line_label):
            return True
        if line_label == "date" or has_keyword_match(DOB_NEGATIVE_PATTERNS, line_label):
            return False

    if has_keyword_match(DOB_EXPLICIT_PATTERNS, local_lower):
        return True
    if has_keyword_match(DOB_NEGATIVE_PATTERNS, local_lower):
        return False

    has_record_context = has_keyword_match(DOB_RECORD_PATTERNS, line_lower) or has_keyword_match(DOB_RECORD_PATTERNS, context_lower)
    has_name = bool(LIKELY_NAME_RE.search(extract_local_window(text, start, end, padding=72)))
    has_row_structure = any(separator in line_text for separator in ("|", "\t", ","))
    return has_record_context and (has_name or has_row_structure)


def email_match_filter(raw_value: str, text: str, start: int, end: int, line_text: str, context_text: str, source_ref: str) -> bool:
    del source_ref
    line_lower = normalize_filter_text(line_text).lower()
    context_lower = normalize_filter_text(context_text).lower()
    local_prefix = normalize_filter_text(text[max(0, start - 56):start]).lower()
    local_window = normalize_filter_text(extract_local_window(text, start, end, padding=96)).lower()
    line_label = last_field_label(extract_line_prefix(text, start))
    header_metadata = line_label in EMAIL_HEADER_LABELS or bool(
        re.match(r"^\s*(from|to|cc|bcc|reply[- ]to|sender)\s*:", line_text, re.IGNORECASE)
    )
    person_context = (
        has_keyword_match(EMAIL_PERSON_PATTERNS, local_prefix)
        or has_keyword_match(EMAIL_PERSON_PATTERNS, line_lower)
        or has_keyword_match(PERSON_RECORD_PATTERNS, line_lower)
        or has_keyword_match(PERSON_RECORD_PATTERNS, context_lower)
        or has_keyword_match(PERSON_RECORD_PATTERNS, local_window)
        or bool(LIKELY_NAME_RE.search(extract_local_window(text, start, end, padding=96)))
        or (line_label and has_keyword_match(EMAIL_PERSON_PATTERNS, line_label))
    )
    service_context = (
        has_keyword_match(EMAIL_SERVICE_PATTERNS, local_prefix)
        or has_keyword_match(EMAIL_SERVICE_PATTERNS, line_lower)
        or has_keyword_match(EMAIL_SERVICE_PATTERNS, context_lower)
        or (line_label and has_keyword_match(EMAIL_SERVICE_PATTERNS, line_label))
    )
    labeled_email = line_label and (
        has_keyword_match(EMAIL_LABEL_PATTERNS, line_label) or has_keyword_match(EMAIL_PERSON_PATTERNS, line_label)
    )
    personal_mailbox = looks_personal_mailbox(raw_value)
    generic_role_mailbox = looks_generic_role_email(raw_value)

    if person_context and not generic_role_mailbox:
        return True
    if service_context or header_metadata:
        return False
    if labeled_email:
        return personal_mailbox or not generic_role_mailbox
    if has_keyword_match(EMAIL_LABEL_PATTERNS, local_prefix) and not has_keyword_match(EMAIL_SERVICE_PATTERNS, local_prefix):
        return personal_mailbox or not generic_role_mailbox
    if person_context and personal_mailbox:
        return True
    return personal_mailbox


def phone_match_filter(raw_value: str, text: str, start: int, end: int, line_text: str, context_text: str, source_ref: str) -> bool:
    del raw_value, source_ref
    line_lower = normalize_filter_text(line_text).lower()
    context_lower = normalize_filter_text(context_text).lower()
    line_label = last_field_label(extract_line_prefix(text, start))

    if line_label and has_keyword_match(PHONE_LABEL_PATTERNS, line_label):
        return True
    if has_keyword_match(PHONE_NEGATIVE_PATTERNS, line_lower) or has_keyword_match(PHONE_NEGATIVE_PATTERNS, context_lower):
        return (
            has_keyword_match(PERSON_RECORD_PATTERNS, line_lower)
            or has_keyword_match(PERSON_RECORD_PATTERNS, context_lower)
            or bool(LIKELY_NAME_RE.search(extract_local_window(text, start, end, padding=72)))
        )
    return True


def ipv4_match_filter(raw_value: str, text: str, start: int, end: int, line_text: str, context_text: str, source_ref: str) -> bool:
    del raw_value, text, start, end, source_ref
    line_lower = normalize_filter_text(line_text).lower()
    context_lower = normalize_filter_text(context_text).lower()

    has_local_ip_label = has_keyword_match(IP_LABEL_PATTERNS, line_lower)
    has_local_personal_context = has_keyword_match(IP_PERSON_PATTERNS, line_lower)
    if has_local_ip_label and has_local_personal_context:
        return True
    if has_keyword_match(IP_NEGATIVE_PATTERNS, line_lower):
        return False
    if has_keyword_match(IP_NEGATIVE_PATTERNS, context_lower):
        return False

    has_ip_label = has_local_ip_label or has_keyword_match(IP_LABEL_PATTERNS, context_lower)
    has_personal_context = has_local_personal_context or has_keyword_match(IP_PERSON_PATTERNS, context_lower)
    return has_ip_label and has_personal_context
