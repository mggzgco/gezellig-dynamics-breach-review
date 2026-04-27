from __future__ import annotations

import re
from datetime import date, datetime
from typing import Optional

from app.pii_normalization import compact_alnum, digits_only


def luhn_check(number: str) -> bool:
    digits = [int(digit) for digit in digits_only(number)]
    if len(digits) < 2:
        return False
    odd_digits = digits[-1::-2]
    even_digits = digits[-2::-2]
    total = sum(odd_digits) + sum(digit * 2 - 9 if digit * 2 > 9 else digit * 2 for digit in even_digits)
    return total % 10 == 0


def aba_check(routing: str) -> bool:
    digits = [int(char) for char in digits_only(routing)]
    if len(digits) != 9:
        return False
    checksum = (
        3 * (digits[0] + digits[3] + digits[6])
        + 7 * (digits[1] + digits[4] + digits[7])
        + (digits[2] + digits[5] + digits[8])
    )
    return checksum % 10 == 0


def sin_check(sin: str) -> bool:
    digits = digits_only(sin)
    if len(digits) != 9 or digits.startswith("0"):
        return False
    return luhn_check(digits)


def iban_check(iban: str) -> bool:
    iban_clean = compact_alnum(iban)
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{4,30}", iban_clean):
        return False
    rearranged = iban_clean[4:] + iban_clean[:4]
    numeric = ""
    for char in rearranged:
        if char.isdigit():
            numeric += char
        else:
            numeric += str(ord(char) - ord("A") + 10)
    return int(numeric) % 97 == 1


def npi_check(npi: str) -> bool:
    digits = digits_only(npi)
    if len(digits) != 10:
        return False
    return luhn_check("80840" + digits)


def bank_account_check(value: str) -> bool:
    digits = digits_only(value)
    if len(digits) < 6 or len(digits) > 17:
        return False
    if len(set(digits)) == 1:
        return False
    return True


def passport_check(value: str) -> bool:
    compact = compact_alnum(value)
    if len(compact) < 6 or len(compact) > 12:
        return False
    return any(char.isdigit() for char in compact)


def drivers_license_check(value: str) -> bool:
    compact = compact_alnum(value)
    if len(compact) < 5 or len(compact) > 20:
        return False
    if not any(char.isdigit() for char in compact):
        return False
    if compact.isdigit() and len(set(compact)) == 1:
        return False
    return True


def mrn_check(value: str) -> bool:
    compact = compact_alnum(value)
    if len(compact) < 5 or len(compact) > 12:
        return False
    digits = digits_only(compact)
    if digits and len(set(digits)) == 1:
        return False
    return any(char.isdigit() for char in compact)


def full_name_check(value: str) -> bool:
    tokens = [token for token in re.split(r"\s+", value.strip()) if token]
    if len(tokens) < 2 or len(tokens) > 4:
        return False
    if not all(re.fullmatch(r"[A-Za-z][A-Za-z'.-]{0,30}", token) for token in tokens):
        return False

    stopwords = {
        "account",
        "address",
        "benefits",
        "birth",
        "card",
        "code",
        "compliance",
        "credential",
        "date",
        "details",
        "diagnosis",
        "dob",
        "documentation",
        "ein",
        "for",
        "full",
        "home",
        "intake",
        "login",
        "member",
        "mobile",
        "mrn",
        "ndc",
        "npi",
        "number",
        "packet",
        "patient",
        "personal",
        "phone",
        "provider",
        "record",
        "records",
        "review",
        "routing",
        "tax",
        "verification",
    }
    normalized_tokens = {token.strip("'.-").lower() for token in tokens}
    return not normalized_tokens & stopwords


_DATE_FORMATS = [
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%m/%d/%Y",
    "%m-%d-%Y",
    "%m/%d/%y",
    "%m-%d-%y",
    "%B %d %Y",
    "%b %d %Y",
    "%d %B %Y",
    "%d %b %Y",
]


def parse_reasonable_date(value: str) -> Optional[date]:
    candidates = {
        value.strip(),
        value.strip().replace(",", ""),
        re.sub(r"\s+", " ", value.strip().replace(",", "")),
    }

    parsed: Optional[date] = None
    for candidate in candidates:
        for date_format in _DATE_FORMATS:
            try:
                parsed = datetime.strptime(candidate, date_format).date()
                break
            except ValueError:
                continue
        if parsed:
            break

    if not parsed or parsed.year < 1800 or parsed.year > 2100:
        return None
    return parsed


def dob_check(value: str) -> bool:
    return parse_reasonable_date(value) is not None


def normalize_dob(value: str) -> str:
    parsed = parse_reasonable_date(value)
    return parsed.isoformat() if parsed else value.strip()
