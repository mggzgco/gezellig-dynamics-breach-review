"""Regulated/sensitive identifier match filters."""

from __future__ import annotations

from app.pii_match_filter_common import (
    BANK_NEGATIVE_PATTERNS,
    BANK_POSITIVE_PATTERNS,
    SSN_LABEL_PATTERNS,
    SSN_NEGATIVE_PATTERNS,
    extract_line_prefix,
    has_keyword_match,
    last_field_label,
    normalize_filter_text,
)


def ssn_match_filter(raw_value: str, text: str, start: int, end: int, line_text: str, context_text: str, source_ref: str) -> bool:
    del text, start, end, source_ref
    line_lower = normalize_filter_text(line_text).lower()
    context_lower = normalize_filter_text(context_text).lower()
    has_ssn_label = has_keyword_match(SSN_LABEL_PATTERNS, line_lower) or has_keyword_match(SSN_LABEL_PATTERNS, context_lower)
    if has_ssn_label:
        return True
    if has_keyword_match(SSN_NEGATIVE_PATTERNS, line_lower) or has_keyword_match(SSN_NEGATIVE_PATTERNS, context_lower):
        return False
    if has_keyword_match(BANK_NEGATIVE_PATTERNS, line_lower) or has_keyword_match(BANK_NEGATIVE_PATTERNS, context_lower):
        return False
    return "-" in raw_value or " " in raw_value


def bank_account_match_filter(raw_value: str, text: str, start: int, end: int, line_text: str, context_text: str, source_ref: str) -> bool:
    del raw_value, end, source_ref
    line_lower = normalize_filter_text(line_text).lower()
    context_lower = normalize_filter_text(context_text).lower()
    line_label = last_field_label(extract_line_prefix(text, start))

    if has_keyword_match(BANK_POSITIVE_PATTERNS, line_lower) or has_keyword_match(BANK_POSITIVE_PATTERNS, context_lower):
        return True
    if line_label in {"checking", "savings"}:
        return True
    if has_keyword_match(BANK_NEGATIVE_PATTERNS, line_lower) or has_keyword_match(BANK_NEGATIVE_PATTERNS, context_lower):
        return False
    return False
