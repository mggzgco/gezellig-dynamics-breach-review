from __future__ import annotations

from difflib import SequenceMatcher
import re
import uuid
from typing import Optional

from app.models import EmailAnalysisResult, PersonRecord
from app.processing.entity_resolution_models import HeaderParticipant


ROLE_STOPWORDS = {
    "admissions",
    "accounts",
    "account",
    "billing",
    "care",
    "center",
    "centre",
    "company",
    "compliance",
    "customer",
    "delivery",
    "department",
    "desk",
    "dev",
    "finance",
    "help",
    "hr",
    "human",
    "insurance",
    "legal",
    "management",
    "marketing",
    "office",
    "operations",
    "payroll",
    "recruiting",
    "resources",
    "sales",
    "service",
    "services",
    "support",
    "success",
    "systems",
    "team",
    "training",
    "university",
}


def extract_name_from_email(email_addr: str) -> Optional[str]:
    if not email_addr or "@" not in email_addr:
        return None

    local_part = email_addr.split("@", 1)[0]
    name = re.sub(r"[._-]+", " ", local_part)
    if any(char.isalpha() for char in name):
        name = re.sub(r"\d+", "", name).strip()
    tokens = [token.capitalize() for token in name.split() if token]
    return " ".join(tokens) if tokens else None


def build_header_participants(result: EmailAnalysisResult) -> list[HeaderParticipant]:
    participants: list[HeaderParticipant] = []
    seen = set()

    def register(email: Optional[str], name: Optional[str], role: str) -> None:
        if not email:
            return
        normalized = email.strip().lower()
        if normalized in seen:
            return
        seen.add(normalized)
        participants.append(HeaderParticipant(email=normalized, name=name.strip() if name else None, role=role))

    register(result.from_address, result.from_name, "sender")
    for index, email in enumerate(result.to_addresses):
        participant_name = result.to_names[index] if index < len(result.to_names) else None
        register(email, participant_name, "recipient")
    for email in result.cc_addresses:
        register(email, None, "cc")
    for email in result.bcc_addresses:
        register(email, None, "bcc")

    return participants


def participant_for_email(email: Optional[str], participants: list[HeaderParticipant]) -> Optional[HeaderParticipant]:
    if not email:
        return None
    email_normalized = email.strip().lower()
    for participant in participants:
        if participant.email == email_normalized:
            return participant
    return None


def participant_for_name(name: Optional[str], participants: list[HeaderParticipant]) -> Optional[HeaderParticipant]:
    if not name:
        return None
    target = normalize_name(name)
    exact_matches = [
        participant for participant in participants if participant.name and normalize_name(participant.name) == target
    ]
    if len(exact_matches) == 1:
        return exact_matches[0]

    if len(participants) == 1 and participants[0].name:
        participant_tokens = set(normalize_name(participants[0].name).split())
        target_tokens = set(target.split())
        if target_tokens and target_tokens.issubset(participant_tokens):
            return participants[0]

    return None


def entity_key(name: Optional[str], email: Optional[str], entity_type: str) -> str:
    if email:
        return f"email:{email.lower()}"
    if name:
        return f"name:{entity_type.lower()}:{normalize_name(name)}"
    return f"entity:{uuid.uuid4()}"


def entity_type_from_role(role: Optional[str]) -> str:
    if not role:
        return "PERSON"
    normalized = role.strip().lower()
    if normalized in {
        "name",
        "full name",
        "email",
        "e-mail",
        "patient",
        "employee",
        "member",
        "customer",
        "client",
        "applicant",
        "student",
        "borrower",
        "guest",
        "traveler",
        "passenger",
        "renter",
        "tenant",
        "buyer",
        "seller",
        "homeowner",
        "driver",
    }:
        return "PERSON"
    return normalized.upper().replace(" ", "_")


def stable_person_id(person: PersonRecord) -> str:
    if person.canonical_email:
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, person.canonical_email))
    if person.canonical_name and person.canonical_name != "UNATTRIBUTED":
        return str(uuid.uuid5(uuid.NAMESPACE_URL, normalize_name(person.canonical_name)))
    return str(uuid.uuid4())


def looks_like_person_name(value: str) -> bool:
    cleaned = clean_name(value)
    if not cleaned:
        return False
    tokens = cleaned.split()
    if len(tokens) < 2 or len(tokens) > 4:
        return False
    lowercase_tokens = {re.sub(r"[^a-z]", "", token.lower()) for token in tokens}
    if lowercase_tokens and lowercase_tokens.issubset(ROLE_STOPWORDS):
        return False
    return all(re.fullmatch(r"(?:[A-Z][A-Za-z'.-]+|[A-Z]{2,})", token) for token in tokens)


def clean_name(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    cleaned = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", value)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,;:")
    return cleaned if cleaned else None


def normalize_name(value: Optional[str]) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"[^A-Za-z ]", " ", value)).strip().upper()


def display_name(normalized_name: str) -> str:
    return " ".join(token.capitalize() for token in normalized_name.split())


def looks_like_name_salutation(block_text: str, recipient_name: str) -> bool:
    if not recipient_name or not block_text:
        return False
    stripped = block_text.strip(" ,;:")
    tokens = normalize_name(stripped).split()
    recipient_tokens = set(normalize_name(recipient_name).split())
    return bool(tokens) and len(tokens) <= 3 and set(tokens).issubset(recipient_tokens)


def names_look_like_ocr_variants(left: Optional[str], right: Optional[str]) -> bool:
    """Detect bounded OCR-style person-name variants such as William/Wiliam."""
    left_tokens = normalize_name(left).split()
    right_tokens = normalize_name(right).split()
    if len(left_tokens) < 2 or len(left_tokens) != len(right_tokens):
        return False

    first_left, *_, last_left = left_tokens
    first_right, *_, last_right = right_tokens
    if first_left[:1] != first_right[:1]:
        return False
    if _edit_distance(first_left, first_right) > 2:
        return False
    if _edit_distance(last_left, last_right) > 2:
        return False
    if SequenceMatcher(None, " ".join(left_tokens), " ".join(right_tokens)).ratio() < 0.84:
        return False
    return True


def _edit_distance(left: str, right: str) -> int:
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)

    previous = list(range(len(right) + 1))
    for left_index, left_char in enumerate(left, start=1):
        current = [left_index]
        for right_index, right_char in enumerate(right, start=1):
            insert_cost = current[right_index - 1] + 1
            delete_cost = previous[right_index] + 1
            replace_cost = previous[right_index - 1] + (0 if left_char == right_char else 1)
            current.append(min(insert_cost, delete_cost, replace_cost))
        previous = current
    return previous[-1]
