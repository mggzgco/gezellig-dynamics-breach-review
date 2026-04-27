"""Post-attribution record merging helpers.

This pass only merges tightly bounded OCR-style name variants so the final
report does not split one person into multiple entities because a scanned
document dropped or swapped one or two characters in the name.
"""

from __future__ import annotations

from app.models import PersonRecord
from app.processing.entity_resolution_utils import names_look_like_ocr_variants


def merge_similar_person_records(persons: list[PersonRecord]) -> list[PersonRecord]:
    """Collapse near-duplicate person records caused by OCR name variants."""
    ordered = sorted(persons, key=_merge_priority, reverse=True)
    merged: list[PersonRecord] = []

    for candidate in ordered:
        target = next((existing for existing in merged if _can_merge(existing, candidate)), None)
        if target is None:
            merged.append(candidate)
            continue
        _merge_into(target, candidate)

    return merged


def _can_merge(primary: PersonRecord, candidate: PersonRecord) -> bool:
    if primary is candidate:
        return False
    if primary.entity_type != "PERSON" or candidate.entity_type != "PERSON":
        return False
    if not primary.canonical_name or not candidate.canonical_name:
        return False
    if primary.canonical_name == "UNATTRIBUTED" or candidate.canonical_name == "UNATTRIBUTED":
        return False
    if primary.canonical_email and candidate.canonical_email and primary.canonical_email != candidate.canonical_email:
        return False
    return names_look_like_ocr_variants(primary.canonical_name, candidate.canonical_name)


def _merge_into(target: PersonRecord, source: PersonRecord) -> None:
    if source.canonical_email and not target.canonical_email:
        target.canonical_email = source.canonical_email

    target.all_emails.update(source.all_emails)
    target.all_names.update(source.all_names)
    for match in source.pii_matches:
        if match not in target.pii_matches:
            target.pii_matches.append(match)
    for email_file in source.source_emails:
        if email_file not in target.source_emails:
            target.source_emails.append(email_file)
    for method in source.attribution_methods:
        if method not in target.attribution_methods:
            target.attribution_methods.append(method)
    for evidence in source.attribution_evidence:
        if evidence not in target.attribution_evidence:
            target.attribution_evidence.append(evidence)

    combined_confidence = (
        (target.attribution_confidence * max(1, len(target.pii_matches) - len(source.pii_matches)))
        + (source.attribution_confidence * max(1, len(source.pii_matches)))
    ) / max(1, len(target.pii_matches))
    target.attribution_confidence = round(max(target.attribution_confidence, combined_confidence), 2)


def _merge_priority(person: PersonRecord) -> tuple[int, int, int, float, int]:
    return (
        1 if person.canonical_email else 0,
        len(person.source_emails),
        len(person.pii_matches),
        person.attribution_confidence,
        len(person.canonical_name or ""),
    )
