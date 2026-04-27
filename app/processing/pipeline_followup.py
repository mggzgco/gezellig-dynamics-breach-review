"""QA-driven deterministic follow-up scanning helpers."""

from __future__ import annotations

import re

from app.models import EmailAnalysisResult
from app.processing.local_llm_file_qa_policy import has_record_like_context
from app.processing.pii_engine import merge_matches, scan_text


FOLLOWUP_TYPE_HINTS: dict[str, tuple[re.Pattern, ...]] = {
    "FULL_NAME": (re.compile(r"(?i)\b(full\s+name|patient\s+name|member\s+name|record\s+owner)\b"),),
    "DOB": (
        re.compile(r"(?i)\b(date\s+of\s+birth|dob|birth\s+date)\b"),
        re.compile(r"(?i)\b(?:0?8|do8|d0b)\s+\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b"),
    ),
    "SSN": (re.compile(r"(?i)\b(ssn|social\s+security|ssh|ssm|s5n)\b"),),
    "ADDRESS": (re.compile(r"(?i)\b(home\s+address|address|mailing\s+address|adress)\b"),),
    "PHONE": (re.compile(r"(?i)\b(phone|mobile|telephone)\b"),),
    "EMAIL": (re.compile(r"(?i)\b(email|e-mail)\b"), re.compile(r"@")),
    "DRIVERS_LICENSE": (re.compile(r"(?i)\b(driver'?s?\s+license|driver\s+license)\b"),),
    "PASSPORT": (re.compile(r"(?i)\bpassport\b"),),
    "MRN": (re.compile(r"(?i)\b(mrn|medical\s+record|record\s+number)\b"),),
    "MEDICARE": (re.compile(r"(?i)\b(medicare|mbi)\b"),),
    "ICD10": (re.compile(r"(?i)\b(icd|diagnosis\s+code)\b"),),
    "NDC": (re.compile(r"(?i)\b(ndc|drug\s+code)\b"),),
    "BANK_ACCOUNT": (re.compile(r"(?i)\b(routing\s+number|account\s+number|bank\s+account|aba)\b"),),
    "CREDIT_CARD": (re.compile(r"(?i)\b(card\s+number|credit\s+card|debit\s+card)\b"),),
    "IBAN": (re.compile(r"(?i)\biban\b"),),
    "EIN": (re.compile(r"(?i)\b(ein|employer\s+identification)\b"),),
}


def apply_bounded_qa_followup(result: EmailAnalysisResult) -> None:
    """Run a narrow deterministic follow-up scan for AI-suspected missing types."""
    review = result.qa_review
    if not review or not review.needs_human_review:
        return

    followup_matches = []
    source_refs = select_followup_sources(result, review.evidence_quotes)
    target_types = set(review.suspected_missing_types) or infer_followup_types(result, source_refs)
    if not target_types:
        review.followup_scanned = bool(source_refs)
        return

    for source_ref in source_refs:
        source_text = result.source_texts.get(source_ref, "")
        if not source_text.strip():
            continue
        followup_matches.extend(
            scan_text(
                source_text,
                source_ref,
                include_types=target_types,
                scan_mode="followup",
            )
        )

    review.followup_scanned = bool(source_refs)
    merged_matches = merge_matches(result.pii_matches, followup_matches)
    existing_keys = {(match.source_ref, match.pii_type, match.normalized_value) for match in result.pii_matches}
    added_matches = [
        match
        for match in merged_matches
        if (match.source_ref, match.pii_type, match.normalized_value) not in existing_keys
    ]
    if not added_matches:
        return

    result.pii_matches = merged_matches
    review.followup_match_count = len(added_matches)
    review.followup_pii_types = sorted({match.pii_type for match in added_matches})
    review.followup_source_refs = sorted({match.source_ref for match in added_matches})
    review.needs_human_review = True
    review.status = "needs_review"
    review.reason = (
        f"{review.reason} Follow-up scan added {len(added_matches)} deterministic match"
        f"{'es' if len(added_matches) != 1 else ''}."
    ).strip()


def select_followup_sources(result: EmailAnalysisResult, evidence_quotes: list[str]) -> list[str]:
    """Pick the most relevant source texts for one bounded follow-up scan."""
    matched_sources: list[str] = []
    normalized_quotes = [normalize_for_followup(quote) for quote in evidence_quotes if quote.strip()]
    for source_ref, source_text in result.source_texts.items():
        normalized_text = normalize_for_followup(source_text)
        if any(quote and quote in normalized_text for quote in normalized_quotes):
            matched_sources.append(source_ref)

    if matched_sources:
        return sorted(dict.fromkeys(matched_sources))

    return sorted(
        result.source_texts,
        key=lambda source_ref: (
            0 if result.source_extractions.get(source_ref) and result.source_extractions[source_ref].ocr_used else 1,
            0 if result.source_extractions.get(source_ref) and result.source_extractions[source_ref].structured else 1,
            0 if " > " in source_ref else 1,
            0 if "(email body)" in source_ref else 1,
            -len(result.source_texts.get(source_ref, "")),
            source_ref,
        ),
    )[:4]


def infer_followup_types(result: EmailAnalysisResult, source_refs: list[str]) -> set[str]:
    """Infer bounded recovery targets when the AI reviewer only flags uncertainty."""
    review = result.qa_review
    combined_text = "\n".join(result.source_texts.get(source_ref, "") for source_ref in source_refs)
    if review:
        combined_text = "\n".join(
            [
                combined_text,
                *(review.evidence_quotes or []),
                review.reason or "",
            ]
        )
    normalized_text = normalize_for_followup(combined_text)
    inferred = {
        pii_type
        for pii_type, patterns in FOLLOWUP_TYPE_HINTS.items()
        if any(pattern.search(normalized_text) for pattern in patterns)
    }

    if inferred:
        return inferred
    if not result.pii_matches and has_record_like_context(result):
        return {"FULL_NAME", "DOB", "ADDRESS"}
    return set()


def normalize_for_followup(value: str) -> str:
    """Whitespace-normalize free text for quote-to-source matching."""
    return " ".join(value.lower().split())
