"""OCR text normalization helpers.

These helpers do not invent new facts. They only repair common OCR damage in
field labels and nearby values so the deterministic detector sees a cleaner,
more structured representation of the text it already extracted.
"""

from __future__ import annotations

import re
from datetime import datetime
from difflib import SequenceMatcher

from app.pii_validation import iban_check


COMMON_WORD_FIXES = {
    "adress": "address",
    "avenus": "avenue",
    "diagnesiscode": "diagnosis code",
    "diagnesis": "diagnosis",
    "identiy": "identity",
    "vertcaion": "verification",
    "atement": "statement",
    "supportcontact": "support contact",
    "follow-updue": "follow-up due",
    "prvacy": "privacy",
}
COMMON_EMAIL_DOMAIN_FIXES = {
    "emailcom": "email.com",
    "gmailcom": "gmail.com",
    "yahoa.com": "yahoo.com",
    "yahoocom": "yahoo.com",
    "yah0o.com": "yahoo.com",
    "yah00.com": "yahoo.com",
    "yahoa.co": "yahoo.co",
    "yahoa.net": "yahoo.net",
    "gmai1.com": "gmail.com",
    "gmai1.co": "gmail.co",
    "outlookcom": "outlook.com",
    "out1ook.com": "outlook.com",
    "outiook.com": "outlook.com",
    "protonmailcom": "protonmail.com",
    "protonmai.com": "protonmail.com",
}

COMMON_TLDS = ("com", "org", "net", "io", "co", "edu", "gov", "us", "ca")
CURRENT_YEAR = datetime.utcnow().year

LABEL_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Full Name", ("full name", "fullname", "full nane")),
    ("Date of Birth", ("date of birth", "birth date", "dob", "d.o.b")),
    ("SSN", ("ssn", "social security number", "social security")),
    ("MRN", ("mrn", "medical record number", "record number")),
    ("Medicare Number", ("medicare number", "medicare", "mbi")),
    ("Diagnosis Code", ("diagnosis code", "icd10", "icd-10", "icd 10")),
    ("NDC", ("ndc", "ndc code", "drug code")),
    ("Home Address", ("home address", "address", "mailing address")),
    ("Personal Email", ("personal email", "email", "e-mail", "email address")),
    ("Mobile Phone", ("mobile phone", "phone", "phone number", "telephone")),
    ("Passport Number", ("passport", "passport number")),
    ("Driver's License Number", ("driver's license number", "driver license number", "drivers license number")),
    ("IBAN", ("iban",)),
    ("Routing Number", ("routing number", "aba", "transit number")),
    ("Account Number", ("account number", "bank account", "acct number")),
)

SHORT_LABEL_RULES = (
    ("DOB", re.compile(r"^\s*(?:d0b|do8|0?8|dob)\b[\s:.-]*(?P<value>.+)$", re.IGNORECASE)),
    ("SSN", re.compile(r"^\s*(?:ssn|ssh|ssm|s5n)\b[\s:.-]*(?P<value>.+)$", re.IGNORECASE)),
    ("MRN", re.compile(r"^\s*(?:mrn|mn|mrn\.|m rn|wn)\b[\s:.-]*(?P<value>.+)$", re.IGNORECASE)),
    ("NDC", re.compile(r"^\s*(?:ndc|nbe|nde)\b[\s:.-]*(?P<value>.+)$", re.IGNORECASE)),
)

DATE_RE = re.compile(r"(?P<month>\d{1,2})[/-](?P<day>\d{1,2})[/-](?P<year>\d{2,4})")
EMAIL_RE = re.compile(
    r"(?P<local>[A-Za-z0-9][A-Za-z0-9._%+\-]{0,62})\s*@\s*(?P<domain>[A-Za-z0-9][A-Za-z0-9.\-]{1,80})",
    re.IGNORECASE,
)
PHONE_RE = re.compile(r"(?<!\d)(?:\+?1[-.\s]?)?(?:\([2-9][0-9]{2}\)|[2-9][0-9]{2})[-.\s]?\d{2,3}[-.\s]?\d{4}(?!\d)")
CAMEL_CASE_RE = re.compile(r"(?<=[a-z])(?=[A-Z])")
STATE_ZIP_RE = re.compile(r"\b([A-Z]{2})(\d{5}(?:-\d{4})?)\b")
ADDRESS_SUFFIX_FIXES = (
    (re.compile(r"\bAvenus\b", re.IGNORECASE), "Avenue"),
    (re.compile(r"\bAvenu\b", re.IGNORECASE), "Avenue"),
    (re.compile(r"\bPd\b", re.IGNORECASE), "Rd"),
    (re.compile(r"\bRd\b", re.IGNORECASE), "Rd"),
)
MEDICARE_DIGIT_POSITIONS = {0, 3, 6, 9, 10}
MEDICARE_TO_DIGIT = str.maketrans({"O": "0", "Q": "0", "I": "1", "L": "1", "Z": "2", "S": "5", "B": "8", "E": "6", "G": "6"})
MEDICARE_TO_ALPHA = str.maketrans({"0": "O", "1": "I", "2": "Z", "5": "S", "8": "B"})
OCR_DIGIT_CONFUSIONS = str.maketrans({"O": "0", "Q": "0", "I": "1", "L": "1", "S": "5", "B": "8"})
IBAN_COUNTRY_LENGTHS = {
    "AL": 28,
    "AT": 20,
    "BE": 16,
    "BG": 22,
    "CH": 21,
    "CY": 28,
    "CZ": 24,
    "DE": 22,
    "DK": 18,
    "EE": 20,
    "ES": 24,
    "FI": 18,
    "FR": 27,
    "GB": 22,
    "GR": 27,
    "HR": 21,
    "HU": 28,
    "IE": 22,
    "IL": 23,
    "IS": 26,
    "IT": 27,
    "LT": 20,
    "LU": 20,
    "LV": 21,
    "MT": 31,
    "NL": 18,
    "NO": 15,
    "PL": 28,
    "PT": 25,
    "RO": 24,
    "SE": 24,
    "SI": 19,
    "SK": 24,
}
IBAN_OCR_ALTERNATIVES = {
    "0": {"0", "O"},
    "O": {"O", "0"},
    "1": {"1", "I", "L", "M"},
    "I": {"I", "1", "L"},
    "L": {"L", "1", "I"},
    "2": {"2", "Z"},
    "Z": {"Z", "2"},
    "5": {"5", "S"},
    "S": {"S", "5"},
    "6": {"6", "G", "E"},
    "G": {"G", "6"},
    "E": {"E", "6"},
    "8": {"8", "B"},
    "B": {"B", "8"},
    "M": {"M", "N", "H", "1"},
    "N": {"N", "M", "H"},
    "H": {"H", "M", "N"},
}
IBAN_INSERTION_CHOICES = tuple(sorted({option for values in IBAN_OCR_ALTERNATIVES.values() for option in values}))
NAME_PARTICLE_TOKENS = {"de", "del", "della", "di", "la", "le", "van", "von", "st"}


def normalize_ocr_lines(lines: list[str]) -> tuple[list[str], list[str]]:
    """Normalize OCR-damaged line text while preserving factual content."""
    normalized_lines: list[str] = []
    changed = False

    for line in lines:
        normalized = normalize_ocr_line(line)
        if normalized != line:
            changed = True
        normalized_lines.append(normalized)

    warnings = ["ocr_text_normalized"] if changed else []
    return normalized_lines, warnings


def normalize_ocr_line(line: str) -> str:
    """Repair one OCR line into a more structured detector-friendly form."""
    line = _basic_cleanup(line)
    line = _repair_email_spacing(line)
    line = _repair_state_zip_spacing(line)

    label_value = _coerce_label_and_value(line)
    if not label_value:
        return line.strip()

    label, value = label_value
    value = _repair_value_for_label(label, value)
    return f"{label}: {value}".strip(" :")


def _basic_cleanup(line: str) -> str:
    cleaned = line.replace("’", "'").replace("‘", "").replace("“", '"').replace("”", '"')
    cleaned = cleaned.replace("|", " | ")
    cleaned = CAMEL_CASE_RE.sub(" ", cleaned)

    for wrong, right in COMMON_WORD_FIXES.items():
        cleaned = re.sub(rf"(?i)\b{re.escape(wrong)}\b", right, cleaned)

    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip(" ,;:")


def _repair_email_spacing(line: str) -> str:
    line = re.sub(r"([A-Za-z0-9._%+\-])\s*[$€£]\s*(?=@)", r"\1", line)
    line = re.sub(r"@\s*([A-Za-z0-9.-]+)\s+[LlI1]?(com|org|net|io|co|edu|gov|us|ca)\b", r"@\1.\2", line, flags=re.IGNORECASE)
    provider_tlds = r"(com|org|net|io|co|edu|gov|us|ca)"
    provider_patterns = (
        (rf"@\s*e\s*mail\s*[LlI1]?\s*{provider_tlds}\b", r"@email.\1"),
        (rf"@\s*g\s*mai\s*[LlI1]?\s*{provider_tlds}\b", r"@gmail.\1"),
        (rf"@\s*y\s*a\s*h\s*o\s*o\s*{provider_tlds}\b", r"@yahoo.\1"),
        (rf"@\s*out\s*look\s*{provider_tlds}\b", r"@outlook.\1"),
        (rf"@\s*proton\s*mail\s*{provider_tlds}\b", r"@protonmail.\1"),
    )
    for pattern, replacement in provider_patterns:
        line = re.sub(pattern, replacement, line, flags=re.IGNORECASE)

    def repl(match: re.Match) -> str:
        local = _normalize_email_local(match.group("local"))
        domain = _normalize_email_domain(match.group("domain"))
        return f"{local}@{domain}"

    repaired = EMAIL_RE.sub(repl, line)
    repaired = re.sub(r"(?<=@)([A-Za-z0-9-]+)(?=(?:com|org|net|io|co|edu|gov|us|ca)\b)", r"\1.", repaired)
    repaired = re.sub(r"\s+\.\s+", ".", repaired)
    return repaired


def _normalize_email_local(local: str) -> str:
    cleaned = re.sub(r"\s+", "", local)
    cleaned = re.sub(r"[^A-Za-z0-9._%+\-]", "", cleaned)
    return cleaned


def _normalize_email_domain(domain: str) -> str:
    cleaned = re.sub(r"\s+", "", domain).lower()
    cleaned = cleaned.replace("|", ".").replace("..", ".")
    if "." not in cleaned:
        compact_match = re.fullmatch(r"([a-z0-9-]+?)(?:[l1i])?(com|org|net|io|co|edu|gov|us|ca)", cleaned)
        if compact_match:
            cleaned = f"{compact_match.group(1)}.{compact_match.group(2)}"
    cleaned = COMMON_EMAIL_DOMAIN_FIXES.get(cleaned, cleaned)
    return cleaned


def _repair_state_zip_spacing(line: str) -> str:
    return STATE_ZIP_RE.sub(r"\1 \2", line)


def _coerce_label_and_value(line: str) -> tuple[str, str] | None:
    for canonical, pattern in SHORT_LABEL_RULES:
        match = pattern.match(line)
        if match:
            return canonical, match.group("value")

    if ":" in line:
        prefix, value = line.split(":", 1)
        matched = _match_label(prefix)
        if matched:
            return matched, value

    if "-" in line[:28]:
        prefix, value = line.split("-", 1)
        matched = _match_label(prefix)
        if matched:
            return matched, value

    candidate = line
    for regex in (EMAIL_RE, DATE_RE, PHONE_RE):
        match = regex.search(line)
        if not match:
            continue
        prefix = line[: match.start()].strip(" ,-.:")
        if not prefix:
            continue
        matched = _match_label(prefix)
        if matched:
            return matched, line[match.start() :]

    if len(candidate.split()) >= 2:
        matched_prefix = _match_leading_label_prefix(candidate)
        if matched_prefix:
            label, prefix = matched_prefix
            return label, candidate[len(prefix) :].strip(" ,-.:")
        prefix_words = candidate.split()[:4]
        prefix = " ".join(prefix_words)
        matched = _match_label(prefix)
        if matched and len(candidate) > len(prefix):
            return matched, candidate[len(prefix) :].strip(" ,-.:")
    return None


def _match_label(prefix: str) -> str | None:
    normalized_prefix = _normalize_label_text(prefix)
    if not normalized_prefix:
        return None

    best_label = None
    best_score = 0.0
    for canonical, aliases in LABEL_RULES:
        for alias in aliases:
            score = SequenceMatcher(None, normalized_prefix, _normalize_label_text(alias)).ratio()
            if score > best_score:
                best_score = score
                best_label = canonical
    if best_score >= 0.76:
        return best_label
    return None


def _match_leading_label_prefix(line: str) -> tuple[str, str] | None:
    words = line.split()
    label_words: list[str] = []
    for word in words[:5]:
        if re.search(r"\d", word):
            break
        label_words.append(word)

    max_words = len(label_words)
    for word_count in range(max_words, 0, -1):
        prefix = " ".join(label_words[:word_count])
        matched = _match_label(prefix)
        if matched:
            return matched, prefix
    return None


def _normalize_label_text(value: str) -> str:
    return re.sub(r"[^a-z]", "", value.lower())


def _repair_value_for_label(label: str, value: str) -> str:
    value = value.strip(" ,;:")
    if label == "Full Name":
        return _repair_name_value(value)
    if label in {"Date of Birth", "DOB"}:
        return _repair_birth_date_value(value)
    if label == "SSN":
        return _repair_ssn_value(value)
    if label == "Personal Email":
        return _repair_email_spacing(value).strip(" ,;:")
    if label == "Home Address":
        return _repair_address_value(value)
    if label == "Diagnosis Code":
        return _repair_diagnosis_code(value)
    if label == "Medicare Number":
        return _repair_medicare_number(value)
    if label == "IBAN":
        return _repair_iban_value(value)
    if label in {"SSN", "MRN", "NDC", "Passport Number", "Driver's License Number", "IBAN", "Routing Number", "Account Number"}:
        return re.sub(r"[|,;]+$", "", value).strip()
    if label == "Mobile Phone":
        return re.sub(r"[|,;]+$", "", value).strip()
    return value


def _repair_name_value(value: str) -> str:
    cleaned = CAMEL_CASE_RE.sub(" ", value)
    tokens = [token for token in re.split(r"\s+", cleaned.strip(" ,;:")) if token]
    merged: list[str] = []
    index = 0
    while index < len(tokens):
        current = tokens[index]
        if index + 1 < len(tokens):
            next_token = tokens[index + 1]
            current_alpha = current.replace("'", "").replace("-", "")
            next_alpha = next_token.replace("'", "").replace("-", "")
            if (
                current_alpha.isalpha()
                and next_alpha.isalpha()
                and current_alpha.lower() not in NAME_PARTICLE_TOKENS
                and next_alpha.lower() not in NAME_PARTICLE_TOKENS
                and len(current_alpha) <= 3
                and len(next_alpha) <= 3
            ):
                looks_split = (
                    next_token.islower()
                    or current.isupper()
                    or next_token.isupper()
                    or (len(tokens) >= 3 and index == 0)
                )
                if looks_split:
                    merged.append(f"{current}{next_token}")
                    index += 2
                    continue
        merged.append(current)
        index += 1

    cleaned = " ".join(merged)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip(" ,;:")


def _repair_birth_date_value(value: str) -> str:
    candidate = _translate_ocr_digits(value)
    match = DATE_RE.search(candidate)
    if not match:
        return value.strip(" ,;:")
    month = int(match.group("month"))
    day = int(match.group("day"))
    year_raw = match.group("year")
    year = int(year_raw)
    if len(year_raw) == 2:
        year += 1900 if year > 30 else 2000
    elif year < 1900 and year_raw.startswith("1"):
        year = int(f"19{year_raw[2:]}")
    elif year > CURRENT_YEAR + 1 and year_raw.startswith("2"):
        year = int(f"19{year_raw[2:]}")
    month = max(1, min(month, 12))
    day = max(1, min(day, 31))
    return f"{month:02d}/{day:02d}/{year:04d}"


def _repair_ssn_value(value: str) -> str:
    candidate = _translate_ocr_digits(value)
    digits = re.sub(r"\D", "", candidate)
    if len(digits) >= 9:
        digits = digits[:9]
        return f"{digits[:3]}-{digits[3:5]}-{digits[5:9]}"
    return re.sub(r"[|,;]+$", "", candidate).strip()


def _repair_address_value(value: str) -> str:
    cleaned = value
    for pattern, replacement in ADDRESS_SUFFIX_FIXES:
        cleaned = pattern.sub(replacement, cleaned)
    cleaned = _repair_state_zip_spacing(cleaned)
    cleaned = re.sub(r"\b([A-Za-z .'-]+)\s+([A-Z]{2})\s+(\d{5}(?:-\d{4})?)\b", r"\1, \2 \3", cleaned)
    cleaned = re.sub(r"\bAdress\b", "Address", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bAvenu\b", "Avenue", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(
        r"\b(avenue|street|road|lane|drive|boulevard|court|place|way|circle|trail|parkway)\b",
        lambda match: match.group(1).title(),
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip(" ,;:")


def _repair_diagnosis_code(value: str) -> str:
    cleaned = value.strip(" ,;:")
    cleaned = cleaned.replace("£", "E").replace("€", "E")
    alnum = re.sub(r"[^A-Za-z0-9]", "", cleaned).upper()
    if len(alnum) >= 3 and alnum[0].isdigit():
        leading_letter = {
            "0": "O",
            "1": "I",
            "2": "Z",
            "5": "S",
            "6": "G",
            "8": "B",
        }.get(alnum[0])
        if leading_letter:
            alnum = f"{leading_letter}{alnum[1:]}"
    if re.fullmatch(r"[A-Z][0-9]{3,4}", alnum):
        return f"{alnum[:3]}.{alnum[3:]}" if len(alnum) > 3 else alnum
    if re.fullmatch(r"[A-Z][0-9]{2}", alnum):
        return alnum
    if re.fullmatch(r"[A-Z][0-9]{2}[0-9A-Z]{1,4}", alnum):
        return f"{alnum[:3]}.{alnum[3:]}" if len(alnum) > 3 else alnum
    return cleaned


def _repair_medicare_number(value: str) -> str:
    alnum = re.sub(r"[^A-Za-z0-9]", "", value).upper()
    if len(alnum) != 11:
        return value.strip(" ,;:")
    characters: list[str] = []
    for index, char in enumerate(alnum):
        if index in MEDICARE_DIGIT_POSITIONS:
            characters.append(char.translate(MEDICARE_TO_DIGIT))
        else:
            characters.append(char.translate(MEDICARE_TO_ALPHA))
    return "".join(characters)


def _repair_iban_value(value: str) -> str:
    cleaned = re.sub(r"[|,;]+$", "", value).strip()
    compact = re.sub(r"[^A-Za-z0-9]", "", cleaned).upper()
    repaired = _repair_iban_candidate(compact)
    return repaired or cleaned


def _repair_iban_candidate(candidate: str) -> str | None:
    if len(candidate) < 8 or not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]+", candidate):
        return None
    if iban_check(candidate):
        return candidate

    country = candidate[:2]
    target_length = IBAN_COUNTRY_LENGTHS.get(country)
    if not target_length:
        return None

    valid_candidates: list[tuple[str, int]] = []

    if len(candidate) == target_length:
        for index in range(4, len(candidate)):
            for replacement in IBAN_OCR_ALTERNATIVES.get(candidate[index], {candidate[index]}):
                if replacement == candidate[index]:
                    continue
                repaired = f"{candidate[:index]}{replacement}{candidate[index + 1:]}"
                if iban_check(repaired):
                    valid_candidates.append((repaired, index))
    elif len(candidate) == target_length - 1:
        for index in range(4, len(candidate) + 1):
            for insertion in IBAN_INSERTION_CHOICES:
                repaired = f"{candidate[:index]}{insertion}{candidate[index:]}"
                if iban_check(repaired):
                    valid_candidates.append((repaired, index))
    elif len(candidate) == target_length + 1:
        for index in range(4, len(candidate)):
            repaired = f"{candidate[:index]}{candidate[index + 1:]}"
            if iban_check(repaired):
                valid_candidates.append((repaired, index))
    else:
        return None

    deduped: dict[str, int] = {}
    for repaired, position in valid_candidates:
        deduped[repaired] = max(position, deduped.get(repaired, -1))

    if len(deduped) == 1:
        return next(iter(deduped))

    rightmost_position = max(deduped.values(), default=-1)
    rightmost_candidates = [candidate for candidate, position in deduped.items() if position == rightmost_position]
    if len(rightmost_candidates) == 1:
        return rightmost_candidates[0]
    return None


def _translate_ocr_digits(value: str) -> str:
    return value.upper().translate(OCR_DIGIT_CONFUSIONS)
