"""Parsing helpers for normalizing local file-QA model output."""

from __future__ import annotations

import re
from typing import Callable, Optional

from app.processing.local_llm_common import StructuredObjectParser


def extract_response_object(raw_text: str, clean_type_list: Callable[[object], list[str]]) -> Optional[dict]:
    """Parse structured or truncated model output into the expected review payload."""
    candidates = [raw_text, StructuredObjectParser.strip_code_fences(raw_text)]
    for candidate in candidates:
        parsed = StructuredObjectParser.parse_dict_like_text(candidate)
        if parsed:
            return parsed

    partial = _extract_partial_response(raw_text, clean_type_list)
    if partial:
        return partial

    start = raw_text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index, char in enumerate(raw_text[start:], start=start):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return StructuredObjectParser.parse_dict_like_text(raw_text[start:index + 1])

    return _extract_partial_response(raw_text[start:], clean_type_list)


def _extract_partial_response(raw_text: str, clean_type_list: Callable[[object], list[str]]) -> Optional[dict]:
    text = StructuredObjectParser.clean_json_text(StructuredObjectParser.strip_code_fences(raw_text))
    bool_match = re.search(r'"?needs_human_review"?\s*:\s*(true|false)', text, re.IGNORECASE)
    confidence_match = re.search(r'"?confidence"?\s*:\s*([0-9]+(?:\.[0-9]+)?)', text, re.IGNORECASE)
    if not bool_match or not confidence_match:
        return None

    return {
        "needs_human_review": bool_match.group(1).lower() == "true",
        "confidence": float(confidence_match.group(1)),
        "suspected_missing_types": _extract_partial_type_list(text, "suspected_missing_types", clean_type_list),
        "questionable_detected_types": _extract_partial_type_list(text, "questionable_detected_types", clean_type_list),
        "evidence_quotes": _extract_partial_string_list(text, "evidence_quotes"),
        "reason": _extract_partial_reason(text),
    }


def _extract_partial_type_list(
    raw_text: str,
    field_name: str,
    clean_type_list: Callable[[object], list[str]],
) -> list[str]:
    list_match = re.search(rf'"?{field_name}"?\s*:\s*(\[[^\]]*)', raw_text, re.IGNORECASE | re.DOTALL)
    if not list_match:
        return []
    return clean_type_list(_extract_partial_string_list(list_match.group(1), None))


def _extract_partial_string_list(raw_text: str, field_name: Optional[str]) -> list[str]:
    target = raw_text
    if field_name:
        list_match = re.search(rf'"?{field_name}"?\s*:\s*(\[[^\]]*)', raw_text, re.IGNORECASE | re.DOTALL)
        if not list_match:
            return []
        target = list_match.group(1)

    values = []
    for value_match in re.finditer(r'"([^"\n]{1,220})"|\'([^\'\n]{1,220})\'', target):
        value = value_match.group(1) or value_match.group(2) or ""
        cleaned = value.strip()
        if cleaned:
            values.append(cleaned)
    return values


def _extract_partial_reason(raw_text: str) -> str:
    reason_match = re.search(r'"?reason"?\s*:\s*"([^"]*)"?', raw_text, re.IGNORECASE | re.DOTALL)
    if reason_match:
        return reason_match.group(1).strip()[:320]
    single_match = re.search(r"'?reason'?\s*:\s*'([^']*)'?", raw_text, re.IGNORECASE | re.DOTALL)
    if single_match:
        return single_match.group(1).strip()[:320]
    return "Local AI QA response was truncated; extracted the available decision fields."
