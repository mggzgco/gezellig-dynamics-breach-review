import logging

from app.models import PersonRecord

logger = logging.getLogger(__name__)


# PII Type weights
PII_WEIGHTS = {
    "SSN": 10.0,
    "SIN": 10.0,
    "CREDIT_CARD": 10.0,
    "BANK_ACCOUNT": 9.0,
    "PASSPORT": 9.0,
    "DRIVERS_LICENSE": 8.0,
    "MEDICARE": 8.0,
    "MRN": 7.0,
    "DOB": 6.0,
    "FULL_NAME": 2.0,
    "ADDRESS": 5.0,
    "ICD10": 5.0,
    "EMAIL": 3.0,
    "PHONE": 3.0,
    "NDC": 4.0,
    "VIN": 4.0,
    "IBAN": 7.0,
    "ZIP": 2.0,
    "NPI": 2.5,
    "EIN": 2.0,
    "IPV4": 1.0,
}


def calculate_risk_score(person: PersonRecord) -> tuple[float, str]:
    """
    Calculate risk score for a person based on PII matches.
    Returns (score, risk_band).
    """
    if not person.pii_matches:
        return 0.0, "NONE"

    # Base score from unique data elements, with a small recurrence bonus
    base_score = 0.0
    pii_types_found = set()
    seen_matches = set()

    for match in person.pii_matches:
        weight = PII_WEIGHTS.get(match.pii_type, 1.0)
        confidence_weight = max(0.5, min(1.0, getattr(match, "confidence", 1.0)))
        key = (match.pii_type, match.normalized_value or match.redacted_value)

        if key in seen_matches:
            base_score += weight * confidence_weight * 0.15
        else:
            base_score += weight * confidence_weight
            seen_matches.add(key)
        pii_types_found.add(match.pii_type)

    # Apply combination multipliers
    multiplier = 1.0

    # Name + sensitive identifiers
    has_name = bool(person.canonical_name or person.canonical_email) or "FULL_NAME" in pii_types_found or "EMAIL" in pii_types_found
    has_ssn = "SSN" in pii_types_found
    has_sin = "SIN" in pii_types_found
    has_cc = "CREDIT_CARD" in pii_types_found
    has_mbi = "MEDICARE" in pii_types_found
    has_dob = "DOB" in pii_types_found
    has_address = "ADDRESS" in pii_types_found
    has_bank = "BANK_ACCOUNT" in pii_types_found or "IBAN" in pii_types_found

    if has_ssn and (has_name or has_dob or has_address):
        multiplier *= 2.0
    if has_sin and (has_name or has_dob or has_address):
        multiplier *= 2.0
    if has_cc and (has_name or has_dob):
        multiplier *= 2.0
    if has_mbi and (has_name or has_dob):
        multiplier *= 2.0
    if has_dob and has_address:
        multiplier *= 1.5
    if has_bank and (has_name or has_address):
        multiplier *= 1.5

    # Volume multipliers
    unique_matches = len(seen_matches)
    high_risk_count = len({(m.pii_type, m.normalized_value or m.redacted_value) for m in person.pii_matches if m.risk_level == "HIGH"})
    if high_risk_count >= 3:
        multiplier *= 1.8

    if unique_matches >= 5:
        multiplier *= 1.3

    # Regulation-specific multiplier
    hipaa_triggered = any(m.hipaa for m in person.pii_matches)
    if hipaa_triggered:
        multiplier *= 1.2

    final_score = base_score * multiplier

    # Determine risk band
    if final_score >= 18:
        risk_band = "CRITICAL"
    elif final_score >= 9:
        risk_band = "HIGH"
    elif final_score >= 4:
        risk_band = "MEDIUM"
    elif final_score >= 1:
        risk_band = "LOW"
    else:
        risk_band = "NONE"

    return final_score, risk_band


def determine_notification_required(person: PersonRecord) -> dict[str, bool]:
    """
    Determine which regulations require notification based on PII found.
    """
    hipaa = False
    ccpa = False
    pipeda = False

    for match in person.pii_matches:
        if match.hipaa and person.highest_risk_level in ("HIGH", "CRITICAL"):
            hipaa = True
        if match.ccpa and person.highest_risk_level != "NONE":
            ccpa = True
        if match.pipeda and person.highest_risk_level in ("MEDIUM", "HIGH", "CRITICAL"):
            pipeda = True

    return {
        "HIPAA": hipaa,
        "CCPA": ccpa,
        "PIPEDA": pipeda,
    }


def update_person_risk(person: PersonRecord) -> None:
    """
    Update person record with risk score and notification flags.
    Modifies person in place.
    """
    score, risk_band = calculate_risk_score(person)
    person.risk_score = score
    person.highest_risk_level = risk_band

    notifications = determine_notification_required(person)
    person.regulations_triggered = notifications
    person.notification_required = any(notifications.values())
