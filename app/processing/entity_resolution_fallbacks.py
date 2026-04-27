"""Fallback ownership decisions used after deterministic candidate scoring."""

from __future__ import annotations

import re
from typing import Optional

from app.pii_match_filter_personal import looks_generic_role_email
from app.models import EmailAnalysisResult, PIIMatch
from app.processing.entity_resolution_models import AttributionDecision, TextBlock
from app.processing.entity_resolution_utils import (
    display_name,
    entity_key,
    extract_name_from_email,
    looks_like_name_salutation,
)


DIRECT_NOTICE_RE = re.compile(r"(?i)\b(?:dear|hello|hi|your|you)\b")
SALUTATION_RE = re.compile(
    r"(?im)^\s*(?:dear|hello|hi)\s+(?P<name>(?:[A-Z][A-Za-z'.-]+|[A-Z]{2,})(?:[ \t]+(?:[A-Z][A-Za-z'.-]+|[A-Z]{2,})){0,2})\s*[,:\n]"
)
RELATIONSHIP_RE = re.compile(
    r"(?i)\b(?:dependent|spouse|child|co-applicant|household|subscriber|patient|member|beneficiary)\b"
)


def direct_notice_fallback(
    match: PIIMatch,
    source_text: str,
    blocks: list[TextBlock],
    block_index: Optional[int],
    result: EmailAnalysisResult,
    participants,
) -> Optional[AttributionDecision]:
    """Use sole-recipient direct-notice language as a narrow ownership fallback."""
    recipients = [participant for participant in participants if participant.role == "recipient"]
    if len(recipients) != 1 or result.cc_addresses or result.bcc_addresses:
        return None
    if ">" in match.source_ref:
        return None

    recipient = recipients[0]
    recipient_name = recipient.name or extract_name_from_email(recipient.email)
    surrounding_blocks = []
    if block_index is not None:
        surrounding_blocks = [
            blocks[index].text
            for index in range(max(0, block_index - 2), min(len(blocks), block_index + 1))
        ]
    direct_context = "\n".join(surrounding_blocks) if surrounding_blocks else source_text
    has_direct_signal = bool(DIRECT_NOTICE_RE.search(direct_context))
    if recipient_name and surrounding_blocks:
        has_direct_signal = has_direct_signal or any(
            looks_like_name_salutation(block, recipient_name) for block in surrounding_blocks
        )
    if not has_direct_signal:
        return None
    if RELATIONSHIP_RE.search(direct_context):
        return None

    confidence = 0.74
    evidence = ["sole-recipient-direct-notice"]
    if recipient_name and direct_context and (
        SALUTATION_RE.search(direct_context)
        or any(looks_like_name_salutation(block, recipient_name) for block in surrounding_blocks)
    ):
        confidence += 0.06
        evidence.append("salutation-matched-recipient")

    return AttributionDecision(
        entity_key=entity_key(recipient_name, recipient.email, "PERSON"),
        canonical_name=recipient_name,
        canonical_email=recipient.email,
        entity_type="PERSON",
        confidence=round(min(confidence, 0.88), 2),
        method="sole_recipient_direct_notice",
        evidence=evidence,
    )


def self_identifying_fallback(match: PIIMatch) -> Optional[AttributionDecision]:
    """Treat literal self-identifying values as owners only when the signal is strong."""
    if match.pii_type == "EMAIL" and match.normalized_value:
        email = match.normalized_value.lower()
        if looks_generic_role_email(email):
            return None
        return AttributionDecision(
            entity_key=entity_key(extract_name_from_email(email), email, "PERSON"),
            canonical_name=extract_name_from_email(email),
            canonical_email=email,
            entity_type="PERSON",
            confidence=0.95,
            method="self_identifying_email",
            evidence=["email-finding-self-identifies-owner"],
        )

    if match.pii_type == "FULL_NAME" and match.normalized_value:
        canonical_name = display_name(match.normalized_value)
        return AttributionDecision(
            entity_key=entity_key(canonical_name, None, "PERSON"),
            canonical_name=canonical_name,
            canonical_email=None,
            entity_type="PERSON",
            confidence=0.9,
            method="self_identifying_name",
            evidence=["name-finding-self-identifies-owner"],
        )

    return None
