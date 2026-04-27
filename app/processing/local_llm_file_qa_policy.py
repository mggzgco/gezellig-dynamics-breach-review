"""Heuristics for deciding when file-level AI QA should run or escalate."""

from __future__ import annotations

import re

from app.models import EmailAnalysisResult


RECORD_ATTACHMENT_KEYWORDS = {
    "application",
    "beneficiary",
    "coverage",
    "claim",
    "claimant",
    "dependent",
    "eligibility",
    "employee",
    "enrollment",
    "household",
    "identity",
    "intake",
    "member",
    "patient",
    "record",
    "review_packet",
    "roster",
    "subscriber",
}
RECORD_ATTACHMENT_EXTENSIONS = {".csv", ".doc", ".docx", ".eml", ".pdf", ".rtf", ".txt", ".xls", ".xlsx", ".zip"}
OPERATIONAL_ATTACHMENT_KEYWORDS = {
    "operations",
    "operational",
    "ops",
    "ticket",
    "faq",
    "notice",
    "digest",
    "status",
    "runbook",
    "snapshot",
    "checklist",
}
FORWARDED_RECORD_MARKERS = {
    "----- original message -----",
    "forwarding the quoted intake excerpt",
    "only the quoted record block should be treated as candidate personal data",
}
SECURITY_REVIEW_MARKERS = {"login ip", "portal sign-in", "user profile snapshot", "suspicious login"}
MULTI_ENTITY_REVIEW_MARKERS = {"co-applicant", "dependent", "spouse", "relationship", "primary", "household"}
SENSITIVE_SCANNED_TYPES = {
    "ADDRESS",
    "BANK_ACCOUNT",
    "CREDIT_CARD",
    "DOB",
    "DRIVERS_LICENSE",
    "EMAIL",
    "FULL_NAME",
    "IBAN",
    "ICD10",
    "MEDICARE",
    "MRN",
    "NDC",
    "PASSPORT",
    "PHONE",
    "SSN",
}
BROKEN_EMAIL_LABEL_RE = re.compile(
    r"(?i)\b(?:personal\s+email|email(?:\s+address)?)\s*:\s*[^\n]{0,120}(?:@|(?:gmail|yahoo|outlook|protonmail)\b)"
)
BROKEN_EMAIL_VALUE_RE = re.compile(
    r"(?i)\b(?:personal\s+email|email(?:\s+address)?)\s*:\s*(?![A-Za-z0-9][A-Za-z0-9._%+\-]{0,62}@(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,24}\b)[^\n]{0,120}(?:@|(?:gmail|yahoo|outlook|protonmail)\b)"
)
BROKEN_LICENSE_LABEL_RE = re.compile(
    r"(?i)\bdriver'?s?\s+licen[sc]e(?:\s+number)?\s*:\s*[A-Z0-9 -]{5,24}\b"
)
BROKEN_IBAN_LABEL_RE = re.compile(r"(?i)\biban\s*:\s*[A-Z0-9 ][A-Z0-9 .-]{10,40}\b")
BROKEN_MEDICARE_LABEL_RE = re.compile(r"(?i)\b(?:medicare(?:\s+number)?|mbi)\s*:\s*[A-Z0-9 ][A-Z0-9 .-]{8,24}\b")


def source_priority(source_ref: str) -> tuple[int, int]:
    """Rank likely record-bearing sources ahead of operational noise sources."""
    source_lower = source_ref.lower()
    if _contains_any_keyword(source_lower, RECORD_ATTACHMENT_KEYWORDS):
        return (0, 0)
    if _contains_any_keyword(source_lower, OPERATIONAL_ATTACHMENT_KEYWORDS):
        return (2, 0)
    if " > " in source_ref:
        return (1, 0)
    return (3, 0)


def has_record_like_attachment(result: EmailAnalysisResult) -> bool:
    """Detect attachments that should not be silently auto-cleared."""
    for filename in _attachment_names(result):
        if not filename:
            continue
        if _contains_any_keyword(filename, OPERATIONAL_ATTACHMENT_KEYWORDS):
            continue
        if _contains_any_keyword(filename, RECORD_ATTACHMENT_KEYWORDS):
            return True
    return False


def has_record_like_context(result: EmailAnalysisResult) -> bool:
    """Detect record-bearing signals from subjects and extracted source refs."""
    if has_record_like_attachment(result):
        return True

    subject_lower = (result.subject or "").lower()
    if _contains_any_keyword(subject_lower, RECORD_ATTACHMENT_KEYWORDS):
        return True

    return any(
        _contains_any_keyword(source_ref.lower(), RECORD_ATTACHMENT_KEYWORDS)
        for source_ref in result.source_extractions
    )


def has_uncertain_extraction(result: EmailAnalysisResult) -> bool:
    """Escalate OCR-heavy or low-confidence extraction paths instead of auto-clearing."""
    if not (has_record_like_context(result) or result.pii_matches):
        return False
    for metadata in result.source_extractions.values():
        if metadata.low_confidence_ocr:
            return True
        if metadata.ocr_used and metadata.structured and not result.pii_matches:
            return True
        if metadata.ocr_used and metadata.ocr_avg_confidence and metadata.ocr_avg_confidence < 78:
            return True
        if any("empty_ocr_output" == warning for warning in metadata.warnings):
            return True
    if has_labeled_identifier_gap(result):
        return True
    return False


def uncertain_extraction_refs(result: EmailAnalysisResult) -> list[str]:
    """Return the most relevant uncertain OCR sources for analyst evidence."""
    refs = [
        source_ref
        for source_ref, metadata in sorted(result.source_extractions.items())
        if metadata.low_confidence_ocr or metadata.ocr_used
    ]
    if refs:
        return refs[:3]
    return [result.subject or result.eml_filename]


def should_review_result(result: EmailAnalysisResult, *, review_all_files: bool) -> bool:
    """Run the local QA model only when the file is materially uncertain or high-value."""
    if review_all_files:
        return True
    if has_uncertain_extraction(result):
        return True
    if needs_policy_review(result):
        return True
    if not result.pii_matches:
        return has_record_like_context(result)

    if any(
        (
            is_forwarded_record_case(result),
            is_security_profile_case(result),
            is_mixed_record_packet_case(result),
            is_sensitive_scanned_record_case(result),
        )
    ):
        return True
    if any(match.confidence < 0.72 for match in result.pii_matches):
        return True
    return False


def needs_policy_review(result: EmailAnalysisResult) -> bool:
    """Detect files that should not be auto-cleared even if the model says so."""
    return any(
        (
            is_multi_entity_review_case(result),
            has_labeled_identifier_gap(result),
        )
    )


def policy_review_reason(result: EmailAnalysisResult) -> str:
    """Return the strongest deterministic reason a file should stay in review."""
    if is_multi_entity_review_case(result):
        return "Multiple related subjects appear in the same file; human review is required."
    if has_labeled_identifier_gap(result):
        return "Labeled record fields were present but at least one sensitive value was not recovered cleanly."
    return "Deterministic review policy requires human review."


def is_forwarded_record_case(result: EmailAnalysisResult) -> bool:
    """Flag quoted-forwarded records where only a subset of the thread is personal data."""
    pii_types = {match.pii_type for match in result.pii_matches}
    if len(pii_types) < 2:
        return False
    combined_text = _combined_source_text(result)
    if any(marker in combined_text for marker in FORWARDED_RECORD_MARKERS):
        return True
    return ">" in combined_text and "full name:" in combined_text


def is_security_profile_case(result: EmailAnalysisResult) -> bool:
    """Flag account-security alerts that mix user identity, contact data, and login IP."""
    pii_types = {match.pii_type for match in result.pii_matches}
    if "IPV4" not in pii_types:
        return False
    if not {"FULL_NAME", "EMAIL", "PHONE"} & pii_types:
        return False
    combined_text = _combined_source_text(result)
    subject_lower = (result.subject or "").lower()
    return any(marker in combined_text for marker in SECURITY_REVIEW_MARKERS) or "suspicious login" in subject_lower


def is_multi_entity_review_case(result: EmailAnalysisResult) -> bool:
    """Flag household/dependent/co-applicant cases that often require analyst verification."""
    combined_text = _combined_source_text(result)
    if _contains_any_keyword(combined_text, MULTI_ENTITY_REVIEW_MARKERS):
        return True
    return any(name.endswith((".csv", ".xlsx", ".docx")) and "household" in name for name in _attachment_names(result))


def is_mixed_record_packet_case(result: EmailAnalysisResult) -> bool:
    """Flag emails that mix likely record attachments with operational noise attachments."""
    if len(result.attachments_processed) < 2:
        return False
    filenames = _attachment_names(result)
    has_record = any(
        _contains_any_keyword(filename, RECORD_ATTACHMENT_KEYWORDS) and not _contains_any_keyword(filename, OPERATIONAL_ATTACHMENT_KEYWORDS)
        for filename in filenames
    )
    has_operational = any(_contains_any_keyword(filename, OPERATIONAL_ATTACHMENT_KEYWORDS) for filename in filenames)
    return has_record and has_operational


def is_sensitive_scanned_record_case(result: EmailAnalysisResult) -> bool:
    """Flag scanned record artifacts that still warrant human review even when detected cleanly."""
    if not result.pii_matches:
        return False
    if not has_record_like_attachment(result):
        return False
    if not (
        any(metadata.ocr_used for metadata in result.source_extractions.values())
        or has_embedded_scanned_artifact_marker(result)
    ):
        return False
    return any(match.pii_type in SENSITIVE_SCANNED_TYPES for match in result.pii_matches)


def has_labeled_identifier_gap(result: EmailAnalysisResult) -> bool:
    """Detect OCR-labeled fields whose values were not recovered into deterministic findings."""
    pii_types = {match.pii_type for match in result.pii_matches}
    for source_ref, source_text in result.source_texts.items():
        metadata = result.source_extractions.get(source_ref)
        if metadata and not (metadata.ocr_used or metadata.structured):
            continue
        text_lower = source_text.lower()
        if "personal email" in text_lower or "email address" in text_lower or "email:" in text_lower:
            if "EMAIL" not in pii_types and BROKEN_EMAIL_VALUE_RE.search(source_text):
                return True
        if "driver" in text_lower and "license" in text_lower:
            if "DRIVERS_LICENSE" not in pii_types and BROKEN_LICENSE_LABEL_RE.search(source_text):
                return True
        if "iban" in text_lower:
            if "IBAN" not in pii_types and BROKEN_IBAN_LABEL_RE.search(source_text):
                return True
        if "medicare" in text_lower or "mbi" in text_lower:
            if "MEDICARE" not in pii_types and BROKEN_MEDICARE_LABEL_RE.search(source_text):
                return True
    return False


def has_embedded_scanned_artifact_marker(result: EmailAnalysisResult) -> bool:
    """Detect flattened archive sources that contain scanned artifact markers."""
    marker_tokens = ("[pdf page", "[rendered page", ".jpg]", ".png]", ".pdf]")
    return any(any(token in text.lower() for token in marker_tokens) for text in result.source_texts.values())


def _attachment_value(attachment, field: str) -> str:
    """Read transitional attachment records that may still be dict-shaped in tests."""
    if hasattr(attachment, field):
        return str(getattr(attachment, field) or "")
    if isinstance(attachment, dict):
        return str(attachment.get(field, "") or "")
    return ""


def _attachment_names(result: EmailAnalysisResult) -> list[str]:
    """Return lowercase attachment names for policy checks."""
    return [
        _attachment_value(attachment, "filename").lower()
        for attachment in result.attachments_processed
        if _attachment_value(attachment, "filename")
    ]


def _contains_any_keyword(text: str, keywords: set[str]) -> bool:
    """Return True when any keyword appears in free text."""
    return any(keyword in text for keyword in keywords)


def _combined_source_text(result: EmailAnalysisResult) -> str:
    """Collapse subject and sources for policy-marker checks."""
    subject = (result.subject or "").lower()
    body = "\n".join(text.lower() for text in result.source_texts.values())
    return f"{subject}\n{body}"
