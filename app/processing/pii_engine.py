import logging
import re
from typing import Iterable, Optional

from app.models import PIIMatch
from app.pii_catalog import PII_CATALOG
from app.pii_pattern_types import PIIPattern

logger = logging.getLogger(__name__)


def scan_text(
    text: str,
    source_ref: str,
    *,
    include_types: Optional[set[str]] = None,
    scan_mode: str = "primary",
) -> list[PIIMatch]:
    """
    Scan text for all configured PII patterns.

    The scanner applies:
    - exact context keyword matching
    - optional format/checksum validation
    - confidence scoring
    - duplicate suppression by normalized value
    """
    if not text:
        return []

    candidates: list[PIIMatch] = []

    for pattern_def in _iter_patterns(include_types):
        for regex in pattern_def.patterns:
            for match in regex.finditer(text):
                try:
                    start, end = match.span(pattern_def.match_group)
                    raw_value = match.group(pattern_def.match_group).strip()
                except IndexError:
                    start, end = match.span()
                    raw_value = match.group().strip()

                if not raw_value:
                    continue

                if _is_test_data(text, start, end, raw_value):
                    continue

                line_text = _extract_line(text, start, end)
                context_text = _extract_context(text, start, end, pattern_def.context_window)
                candidate = _build_match(
                    text=text,
                    raw_value=raw_value,
                    start=start,
                    end=end,
                    source_ref=source_ref,
                    line_text=line_text,
                    context_text=context_text,
                    pattern_def=pattern_def,
                    scan_mode=scan_mode,
                )
                if candidate:
                    candidates.append(candidate)

    return _dedupe_matches(candidates)


def merge_matches(existing: Iterable[PIIMatch], new_matches: Iterable[PIIMatch]) -> list[PIIMatch]:
    """Merge and deduplicate two match collections using the standard scanner rules."""
    return _dedupe_matches([*existing, *new_matches])


def _build_match(
    text: str,
    raw_value: str,
    start: int,
    end: int,
    source_ref: str,
    line_text: str,
    context_text: str,
    pattern_def: PIIPattern,
    scan_mode: str,
) -> PIIMatch | None:
    evidence: list[str] = []
    confidence = pattern_def.base_confidence

    match_filter = pattern_def.match_filter
    if match_filter:
        try:
            if not match_filter(raw_value, text, start, end, line_text, context_text, source_ref):
                return None
        except Exception as exc:
            logger.debug("Match filter failed for %s in %s: %s", pattern_def.name, source_ref, exc)
            return None

    validator = pattern_def.validator
    if validator:
        try:
            if not validator(raw_value):
                return None
            confidence += 0.08
            evidence.append("validated")
        except Exception as exc:
            logger.debug("Validation failed for %s in %s: %s", pattern_def.name, source_ref, exc)
            return None

    strong_hits = _find_keywords(pattern_def.strong_context_patterns, line_text)
    context_hits = _find_keywords(pattern_def.context_patterns, context_text)
    source_level_hits: list[str] = []
    negative_hits = list(
        dict.fromkeys(
            _find_keywords(pattern_def.negative_context_patterns, line_text)
            + _find_keywords(pattern_def.negative_context_patterns, context_text)
        )
    )

    if strong_hits:
        confidence += min(0.18, 0.06 * len(strong_hits))
        evidence.append(f"label:{strong_hits[0]}")
    elif context_hits:
        confidence += min(0.1, 0.04 * len(context_hits))
        evidence.append(f"context:{context_hits[0]}")
    elif scan_mode == "followup":
        source_level_hits = _find_keywords(pattern_def.strong_context_patterns, text) or _find_keywords(
            pattern_def.context_patterns,
            text,
        )
        if source_level_hits:
            confidence += min(0.05, 0.02 * len(source_level_hits))
            evidence.append(f"followup-context:{source_level_hits[0]}")

    if negative_hits:
        penalty = min(0.08, 0.04 * len(negative_hits)) if strong_hits else min(0.24, 0.08 * len(negative_hits))
        confidence -= penalty
        evidence.append(f"negative:{negative_hits[0]}")

    if pattern_def.requires_context and not (strong_hits or context_hits or source_level_hits):
        return None

    normalized_value = _normalize_value(raw_value, pattern_def)
    if not normalized_value:
        return None

    confidence = max(0.0, min(1.0, confidence))
    min_confidence = pattern_def.min_confidence
    if scan_mode == "followup":
        min_confidence = max(0.0, min_confidence - 0.04)
    if confidence < min_confidence:
        return None

    redacted = _redact_value(raw_value, pattern_def.name)
    excerpt = _build_excerpt(text, start, end, redacted)
    detection_method = pattern_def.detection_method
    if strong_hits and "context" not in detection_method:
        detection_method = f"{detection_method}+context"
    if scan_mode == "followup":
        detection_method = f"{detection_method}+followup"
        evidence.append("qa_followup_scan")

    return PIIMatch(
        pii_type=pattern_def.name,
        pii_category=pattern_def.category,
        pii_subtype=pattern_def.subtype,
        risk_level=pattern_def.risk_level,
        redacted_value=redacted,
        excerpt=excerpt,
        source_ref=source_ref,
        char_offset=start,
        confidence=round(confidence, 2),
        detection_method=detection_method,
        hipaa=pattern_def.hipaa,
        ccpa=pattern_def.ccpa,
        pipeda=pattern_def.pipeda,
        notification_required=pattern_def.notification_required,
        normalized_value=normalized_value,
        evidence=evidence,
    )


def _iter_patterns(include_types: Optional[set[str]]) -> list[PIIPattern]:
    if not include_types:
        return PII_CATALOG
    return [pattern for pattern in PII_CATALOG if pattern.name in include_types]


def _extract_context(text: str, start: int, end: int, window: int) -> str:
    context_start = max(0, start - window)
    context_end = min(len(text), end + window)
    return text[context_start:context_end]


def _extract_line(text: str, start: int, end: int) -> str:
    line_start = text.rfind("\n", 0, start)
    line_end = text.find("\n", end)
    if line_start == -1:
        line_start = 0
    else:
        line_start += 1
    if line_end == -1:
        line_end = len(text)
    return text[line_start:line_end]


def _find_keywords(patterns: list[re.Pattern], text: str) -> list[str]:
    hits: list[str] = []
    for pattern in patterns:
        hit = pattern.search(text)
        if hit:
            hits.append(hit.group(0))
    return hits


def _normalize_value(value: str, pattern_def: PIIPattern) -> str:
    if pattern_def.normalizer:
        return pattern_def.normalizer(value)
    return re.sub(r"\s+", " ", value).strip()


def _dedupe_matches(matches: list[PIIMatch]) -> list[PIIMatch]:
    """
    Keep the best candidate for each normalized value within a source/type pair.
    """
    best_by_key: dict[tuple[str, str, str], PIIMatch] = {}

    for match in matches:
        dedupe_value = match.normalized_value or match.redacted_value
        if match.pii_type == "FULL_NAME":
            dedupe_key = (match.source_ref, match.pii_type, f"{dedupe_value}@{match.char_offset}")
        else:
            dedupe_key = (match.source_ref, match.pii_type, dedupe_value)
        current = best_by_key.get(dedupe_key)
        if current is None:
            best_by_key[dedupe_key] = match
            continue

        current_score = (current.confidence, len(current.evidence), -current.char_offset)
        candidate_score = (match.confidence, len(match.evidence), -match.char_offset)
        if candidate_score > current_score:
            best_by_key[dedupe_key] = match

    return sorted(best_by_key.values(), key=lambda item: (item.source_ref, item.char_offset, item.pii_type))


def _is_test_data(text: str, start: int, end: int, value: str) -> bool:
    """
    Filter obvious sample/demo fixtures and canonical fake values.
    """
    marker_context = _extract_context(text, start, end, 200).lower()
    test_markers = (
        "[sample]",
        "[test]",
        "[placeholder]",
        "[fake]",
        "sample ",
        "test ",
        "demo ",
        "mock ",
        "example ",
    )

    if any(marker in marker_context for marker in test_markers):
        return True

    raw_normalized = re.sub(r"[^A-Za-z0-9@]", "", value).lower()
    fake_values = {
        "123456789",
        "5555550000",
        "4532123456789010",
        "9876543210",
    }
    if raw_normalized in fake_values:
        return True

    fake_emails = {
        "test@example.com",
        "test@test.com",
        "demo@demo.com",
        "sample@example.com",
        "example@example.com",
        "user@test.com",
        "admin@test.com",
    }
    if "@" in value.lower() and value.lower() in fake_emails:
        return True

    return False


def _redact_value(value: str, pii_type: str) -> str:
    """Redact PII value for safe logging/reporting."""
    if pii_type == "SSN":
        digits = re.sub(r"\D", "", value)
        return f"XXX-XX-{digits[-4:]}" if len(digits) >= 4 else "XXX-XX-XXXX"

    if pii_type == "SIN":
        digits = re.sub(r"\D", "", value)
        return f"XXX-XXX-{digits[-3:]}" if len(digits) >= 3 else "XXX-XXX-XXX"

    if pii_type == "CREDIT_CARD":
        digits = re.sub(r"\D", "", value)
        return f"****-****-****-{digits[-4:]}" if len(digits) >= 4 else "****-****-****-****"

    if pii_type == "BANK_ACCOUNT":
        return "****-ACCOUNT-****"

    if pii_type == "EMAIL":
        if "@" in value:
            name, domain = value.split("@", 1)
            if len(name) <= 1:
                return f"*@{domain}"
            return f"{name[0]}{'*' * (len(name) - 1)}@{domain}"
        return "***@***.***"

    if pii_type == "PHONE":
        return "(XXX) XXX-XXXX"

    if pii_type in {"DOB", "ZIP", "ADDRESS", "PASSPORT", "DRIVERS_LICENSE", "MRN", "FULL_NAME"}:
        return f"[REDACTED:{pii_type}]"

    if len(value) > 4:
        return value[:2] + "*" * (len(value) - 4) + value[-2:]
    return "*" * len(value)


def _build_excerpt(text: str, start: int, end: int, replacement: str, context_chars: int = 80) -> str:
    """
    Build a redacted excerpt showing the match in context.
    """
    excerpt_start = max(0, start - context_chars)
    excerpt_end = min(len(text), end + context_chars)
    before = text[excerpt_start:start]
    after = text[end:excerpt_end]
    excerpt = f"...{before}{replacement}{after}..."
    excerpt = re.sub(r"\s+", " ", excerpt).strip()
    return excerpt[:320]
