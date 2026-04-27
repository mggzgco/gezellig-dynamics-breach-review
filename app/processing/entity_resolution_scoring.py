"""Candidate scoring and deterministic candidate selection helpers."""

from __future__ import annotations

from typing import Optional

from app.models import PIIMatch
from app.processing.entity_resolution_models import AttributionDecision, EntityMention, ScoredCandidate
from app.processing.entity_resolution_utils import (
    entity_key,
    entity_type_from_role,
    extract_name_from_email,
    normalize_name,
    participant_for_email,
    participant_for_name,
)


def score_candidates(
    match: PIIMatch,
    candidate_mentions: list[EntityMention],
    participants,
) -> list[ScoredCandidate]:
    """Score extracted entity mentions against a finding using local evidence."""
    scored_candidates: list[ScoredCandidate] = []

    for mention in candidate_mentions:
        score = mention.confidence
        evidence = list(mention.evidence)
        canonical_name = mention.name
        canonical_email = mention.email

        score += 0.04 if mention.same_block else -0.06

        if canonical_email and match.pii_type == "EMAIL" and canonical_email == match.normalized_value:
            score += 0.12
            evidence.append("finding-email-matched-anchor")

        if canonical_name and match.pii_type == "FULL_NAME" and normalize_name(canonical_name) == match.normalized_value:
            score += 0.12
            evidence.append("finding-name-matched-anchor")

        if canonical_name and not canonical_email:
            participant = participant_for_name(canonical_name, participants)
            if participant:
                canonical_email = participant.email
                score += 0.05
                evidence.append("header-participant-matched-name")

        if canonical_email and not canonical_name:
            participant = participant_for_email(canonical_email, participants)
            if participant and participant.name:
                canonical_name = participant.name
                score += 0.04
                evidence.append("header-participant-matched-email")

        if canonical_email and not canonical_name:
            canonical_name = extract_name_from_email(canonical_email)

        scored_candidates.append(
            ScoredCandidate(
                canonical_name=canonical_name,
                canonical_email=canonical_email,
                role=mention.role,
                score=max(0.0, min(0.99, score)),
                method=mention.method,
                evidence=evidence,
                same_block=mention.same_block,
            )
        )

    return dedupe_scored_candidates(scored_candidates)


def decision_from_candidates(scored_candidates: list[ScoredCandidate], participants) -> Optional[AttributionDecision]:
    """Select the strongest deterministic candidate and normalize its identity."""
    if not scored_candidates:
        return None

    best_candidate = max(
        scored_candidates,
        key=lambda candidate: (
            candidate.score,
            len(candidate.evidence),
            candidate.canonical_email or "",
            candidate.canonical_name or "",
        ),
    )

    canonical_name = best_candidate.canonical_name
    canonical_email = best_candidate.canonical_email
    if canonical_name and not canonical_email:
        participant = participant_for_name(canonical_name, participants)
        if participant:
            canonical_email = participant.email

    if canonical_email and not canonical_name:
        participant = participant_for_email(canonical_email, participants)
        if participant and participant.name:
            canonical_name = participant.name

    if not canonical_name and canonical_email:
        canonical_name = extract_name_from_email(canonical_email)

    entity_type = entity_type_from_role(best_candidate.role)
    return AttributionDecision(
        entity_key=entity_key(canonical_name, canonical_email, entity_type),
        canonical_name=canonical_name,
        canonical_email=canonical_email,
        entity_type=entity_type,
        confidence=round(best_candidate.score, 2),
        method=best_candidate.method,
        evidence=list(best_candidate.evidence),
    )


def dedupe_scored_candidates(scored_candidates: list[ScoredCandidate]) -> list[ScoredCandidate]:
    """Keep the strongest scored candidate for each canonical identity tuple."""
    deduped: dict[tuple[str, str, str], ScoredCandidate] = {}
    for candidate in scored_candidates:
        key = (
            normalize_name(candidate.canonical_name),
            (candidate.canonical_email or "").lower(),
            candidate.role or "",
        )
        current = deduped.get(key)
        if current is None or candidate.score > current.score:
            deduped[key] = candidate
    return list(deduped.values())
