from __future__ import annotations

import re
from typing import Optional

from app.pii_match_filter_personal import looks_generic_role_email
from app.processing.entity_resolution_models import EntityMention, HeaderParticipant, TextBlock
from app.processing.entity_resolution_utils import (
    clean_name,
    extract_name_from_email,
    looks_like_person_name,
    participant_for_email,
    participant_for_name,
)


EMAIL_REGEX = (
    r"[A-Za-z0-9](?:[A-Za-z0-9._%+\-]{0,62}[A-Za-z0-9])?"
    r"@(?:[A-Za-z0-9](?:[A-Za-z0-9\-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,24}"
)
NAME_REGEX = r"(?:[A-Z][A-Za-z'.-]+|[A-Z]{2,})(?: +(?:[A-Z][A-Za-z'.-]+|[A-Z]{2,})){1,3}"
SALUTATION_NAME_REGEX = r"(?:[A-Z][A-Za-z'.-]+|[A-Z]{2,})(?: +(?:[A-Z][A-Za-z'.-]+|[A-Z]{2,})){0,2}"

EMAIL_RE = re.compile(EMAIL_REGEX, re.IGNORECASE)
INLINE_NAME_EMAIL_RE = re.compile(rf"\b(?P<name>{NAME_REGEX})\s*<(?P<email>{EMAIL_REGEX})>", re.IGNORECASE)
LABELED_NAME_RE = re.compile(
    rf"(?im)\b(?P<label>full\s+name|name|patient|employee|member|customer|client|applicant|student|borrower|dependent|spouse|child|parent|subscriber|insured|guest|traveler|passenger|renter|tenant|buyer|seller|homeowner|driver|insured\s+party)\b(?:\s+name)?\s*[:#-]\s*(?P<name>{NAME_REGEX})"
)
LABELED_EMAIL_RE = re.compile(
    rf"(?im)\b(?P<label>email|e-mail|contact\s+email|patient\s+email|employee\s+email|member\s+email)\b\s*[:#-]\s*(?P<email>{EMAIL_REGEX})"
)
SALUTATION_RE = re.compile(rf"(?im)^\s*(?:dear|hello|hi)\s+(?P<name>{SALUTATION_NAME_REGEX})\s*[,:\n]")
TABULAR_NAME_LABELS = {
    "full name",
    "name",
    "patient",
    "patient name",
    "employee",
    "employee name",
    "member",
    "member name",
    "dependent",
    "dependent name",
    "subscriber",
    "subscriber name",
    "customer",
    "customer name",
}
TABULAR_EMAIL_LABELS = {
    "email",
    "e-mail",
    "personal email",
    "contact email",
    "member email",
    "patient email",
    "employee email",
}


def build_blocks(source_ref: str, text: str) -> list[TextBlock]:
    blocks: list[TextBlock] = []
    current_lines: list[str] = []
    current_start: Optional[int] = None
    current_end: Optional[int] = None
    offset = 0

    def flush() -> None:
        nonlocal current_lines, current_start, current_end
        if current_lines and current_start is not None and current_end is not None:
            block_text = "\n".join(current_lines).strip()
            if block_text:
                blocks.append(TextBlock(source_ref=source_ref, start=current_start, end=current_end, text=block_text))
        current_lines = []
        current_start = None
        current_end = None

    for raw_line in text.splitlines(True):
        line = raw_line.rstrip("\n")
        stripped = line.strip()

        if not stripped:
            flush()
            offset += len(raw_line)
            continue

        is_tabular = "\t" in line
        is_marker = (
            stripped.startswith("[Sheet:")
            or stripped.startswith("[ZIP member:")
            or stripped.startswith("Attachment filename:")
        )

        if is_tabular or is_marker:
            flush()
            blocks.append(TextBlock(source_ref=source_ref, start=offset, end=offset + len(raw_line), text=stripped))
            offset += len(raw_line)
            continue

        if current_start is None:
            current_start = offset
        current_lines.append(stripped)
        current_end = offset + len(raw_line)
        offset += len(raw_line)

    flush()

    if not blocks and text.strip():
        blocks.append(TextBlock(source_ref=source_ref, start=0, end=len(text), text=text.strip()))

    return blocks


def find_block_index(blocks: list[TextBlock], offset: int) -> Optional[int]:
    for index, block in enumerate(blocks):
        if block.start <= offset <= block.end:
            return index
    return 0 if blocks else None


def neighbor_mentions(
    blocks: list[TextBlock],
    block_index: Optional[int],
    participants: list[HeaderParticipant],
) -> list[EntityMention]:
    mentions: list[EntityMention] = []
    if block_index is None:
        return mentions

    neighbor_indexes = [
        idx
        for idx in (
            block_index - 3,
            block_index - 2,
            block_index - 1,
            block_index + 1,
            block_index + 2,
            block_index + 3,
        )
        if 0 <= idx < len(blocks)
    ]
    for index in neighbor_indexes:
        distance = abs(index - block_index)
        for mention in extract_mentions(blocks[index].text, participants):
            mention.same_block = False
            mention.confidence = max(0.0, mention.confidence - (0.08 * distance))
            mention.evidence.append(f"neighboring-block-anchor:{distance}")
            mentions.append(mention)
    return mentions


def extract_mentions(block_text: str, participants: list[HeaderParticipant]) -> list[EntityMention]:
    mentions: list[EntityMention] = []

    for match in INLINE_NAME_EMAIL_RE.finditer(block_text):
        name = match.group("name").strip()
        email = match.group("email").strip().lower()
        if looks_like_person_name(name):
            mentions.append(
                EntityMention(
                    name=clean_name(name),
                    email=email,
                    confidence=0.97,
                    method="inline_name_email_pair",
                    evidence=["inline-name-email-pair"],
                )
            )

    name_mentions: list[tuple[str, str, int]] = []
    for match in LABELED_NAME_RE.finditer(block_text):
        label = match.group("label").strip().lower()
        name = clean_name(match.group("name"))
        if looks_like_person_name(name or ""):
            name_mentions.append((label, name or "", match.start("name")))

    email_mentions: list[tuple[str, str, int]] = []
    for match in LABELED_EMAIL_RE.finditer(block_text):
        label = match.group("label").strip().lower()
        email_mentions.append((label, match.group("email").strip().lower(), match.start("email")))

    for label, name, position in name_mentions:
        paired_email = None
        if email_mentions:
            same_role_email = next(
                (
                    email
                    for email_label, email, email_pos in email_mentions
                    if abs(email_pos - position) <= 140 and email_label.startswith(label.split()[0])
                ),
                None,
            )
            nearby_email = next(
                (email for _, email, email_pos in email_mentions if abs(email_pos - position) <= 140),
                None,
            )
            paired_email = same_role_email or nearby_email

        participant = participant_for_name(name, participants)
        confidence = 0.9
        evidence = [f"label:{label}"]
        if paired_email:
            confidence += 0.05
            evidence.append("paired-labeled-email")
        elif participant:
            paired_email = participant.email
            confidence += 0.03
            evidence.append("header-email-linked-to-name")

        mentions.append(
            EntityMention(
                name=name,
                email=paired_email,
                role=label,
                confidence=min(confidence, 0.98),
                method="same_block_label",
                evidence=evidence,
            )
        )

    for label, email, _ in email_mentions:
        if looks_generic_role_email(email):
            participant = participant_for_email(email, participants)
            if not participant or not participant.name:
                continue
        participant = participant_for_email(email, participants)
        mentions.append(
            EntityMention(
                name=participant.name if participant else extract_name_from_email(email),
                email=email,
                role=label,
                confidence=0.9 if participant else 0.84,
                method="same_block_email_label",
                evidence=[f"label:{label}"],
            )
        )

    tabular_mention = extract_tabular_row_mention(block_text, participants)
    if tabular_mention:
        mentions.append(tabular_mention)

    salutation = SALUTATION_RE.search(block_text)
    if salutation:
        saluted_name = clean_name(salutation.group("name"))
        participant = participant_for_name(saluted_name, participants)
        mentions.append(
            EntityMention(
                name=participant.name if participant and participant.name else saluted_name,
                email=participant.email if participant else None,
                confidence=0.82 if participant else 0.74,
                method="salutation_match",
                evidence=["salutation-anchor"],
            )
        )

    inline_emails = [
        email.lower()
        for email in EMAIL_RE.findall(block_text)
        if not looks_generic_role_email(email.lower()) or participant_for_email(email.lower(), participants)
    ]
    if len(set(inline_emails)) == 1:
        email = inline_emails[0]
        participant = participant_for_email(email, participants)
        mentions.append(
            EntityMention(
                name=participant.name if participant else extract_name_from_email(email),
                email=email,
                confidence=0.78 if participant else 0.72,
                method="single_inline_email",
                evidence=["single-inline-email"],
            )
        )

    return dedupe_mentions(mentions)


def extract_tabular_row_mention(
    block_text: str,
    participants: list[HeaderParticipant],
) -> Optional[EntityMention]:
    if "\t" not in block_text:
        return None

    cells = [cell.strip() for cell in block_text.split("\t") if cell.strip()]
    if not cells:
        return None

    labeled_cells = []
    for cell in cells:
        if ":" not in cell:
            continue
        label, value = cell.split(":", 1)
        labeled_cells.append((label.strip().lower(), value.strip()))

    name = next(
        (
            clean_name(value)
            for label, value in labeled_cells
            if label in TABULAR_NAME_LABELS and looks_like_person_name(value)
        ),
        None,
    )
    email_match = next(
        (
            EMAIL_RE.search(value)
            for label, value in labeled_cells
            if label in TABULAR_EMAIL_LABELS and EMAIL_RE.search(value)
        ),
        None,
    )

    if not name and not email_match:
        header_like_row = not labeled_cells and all(
            ":" not in cell and not any(char.isdigit() for char in cell) and len(cell.split()) <= 4
            for cell in cells
        )
        if header_like_row:
            return None

        name = next((clean_name(cell) for cell in cells if looks_like_person_name(cell)), None)
        email_match = next((EMAIL_RE.search(cell) for cell in cells if EMAIL_RE.search(cell)), None)

    email = email_match.group(0).lower() if email_match else None

    if not name and not email:
        return None

    participant = participant_for_name(name, participants) if name else participant_for_email(email, participants)
    if participant:
        email = email or participant.email
        name = name or participant.name

    confidence = 0.93 if name and email else 0.82
    evidence = ["tabular-row-anchor"]
    if participant:
        confidence += 0.03
        evidence.append("header-participant-link")

    return EntityMention(
        name=name,
        email=email,
        confidence=min(confidence, 0.98),
        method="tabular_row",
        evidence=evidence,
    )


def dedupe_mentions(mentions: list[EntityMention]) -> list[EntityMention]:
    deduped: dict[tuple[str, str, str], EntityMention] = {}
    for mention in mentions:
        key = (
            clean_name(mention.name) or "",
            (mention.email or "").lower(),
            mention.role or "",
        )
        current = deduped.get(key)
        if current is None or mention.confidence > current.confidence:
            deduped[key] = mention
    return list(deduped.values())
