from __future__ import annotations

import random
from dataclasses import dataclass

from app.pii_validation import aba_check


BENCHMARK_SEED = 20260421
DEFAULT_BENCHMARK_FILE_COUNT = 300
DEFAULT_BENCHMARK_PROFILE = "baseline"
REALWORLD_V2_PROFILE = "realworld_v2"
REALWORLD_V3_PROFILE = "realworld_v3"
REALWORLD_V4_PROFILE = "realworld_v4"
GROUND_TRUTH_FILENAME = "ground_truth.json"
GROUND_TRUTH_SUMMARY_FILENAME = "GROUND_TRUTH_SUMMARY.md"


FIRST_NAMES = [
    "Aaliyah",
    "Amelia",
    "Ava",
    "Benjamin",
    "Caleb",
    "Charlotte",
    "Daniel",
    "David",
    "Elena",
    "Elijah",
    "Emma",
    "Ethan",
    "Grace",
    "Henry",
    "Isabella",
    "Jack",
    "James",
    "Liam",
    "Lucas",
    "Mason",
    "Mia",
    "Noah",
    "Olivia",
    "Sophia",
    "William",
]

LAST_NAMES = [
    "Anderson",
    "Brooks",
    "Carter",
    "Chen",
    "Davis",
    "Foster",
    "Garcia",
    "Hughes",
    "Johnson",
    "Kim",
    "Martinez",
    "Miller",
    "Nguyen",
    "Patel",
    "Price",
    "Ramirez",
    "Robinson",
    "Singh",
    "Taylor",
    "Thomas",
    "Walker",
    "Washington",
    "Williams",
    "Wilson",
    "Young",
]

STREET_NAMES = [
    "Riverview",
    "Maple",
    "Cedar",
    "Hillcrest",
    "Oak",
    "Willow",
    "Sunset",
    "Pine",
    "Bridgewater",
    "Lakeview",
    "Meadow",
    "Park",
    "Walnut",
]

STREET_SUFFIXES = ["St", "Street", "Ave", "Avenue", "Dr", "Drive", "Rd", "Road", "Ln", "Lane", "Way", "Ct"]

LOCATIONS = [
    ("Austin", "TX", "78704"),
    ("Portland", "OR", "97214"),
    ("Phoenix", "AZ", "85016"),
    ("Denver", "CO", "80203"),
    ("Atlanta", "GA", "30309"),
    ("Nashville", "TN", "37212"),
    ("Madison", "WI", "53703"),
    ("Richmond", "VA", "23220"),
    ("Columbus", "OH", "43215"),
    ("Charlotte", "NC", "28203"),
    ("Minneapolis", "MN", "55408"),
    ("Tampa", "FL", "33606"),
]

CONSUMER_DOMAINS = ["gmail.com", "yahoo.com", "outlook.com", "email.com", "protonmail.com"]
WORK_DOMAINS = ["company.com", "healthsystem.org", "benefits.co", "services.net", "enterprise.io"]
ORG_NAMES = [
    "North Ridge Health",
    "Blue Harbor Insurance",
    "Evergreen Logistics",
    "Lakeview Benefits",
    "Cedar Point Retail",
    "Pioneer Financial",
    "Summit Legal Group",
    "Brightline Education",
    "Horizon Workforce",
    "Stonebridge Services",
]
DIAGNOSIS_CODES = ["E11.9", "I10", "J45.909", "M54.5", "F41.1", "K21.9"]
NDC_CODES = ["00597-0087-17", "0781-1506-10", "16729-0117-11", "00074-4337-13"]
TEST_CARD_NUMBERS = [
    "4111 1111 1111 1111",
    "5555 5555 5555 4444",
    "4000 0000 0000 9995",
    "3782 822463 10005",
]
IBAN_NUMBERS = [
    "GB82 WEST 1234 5698 7654 32",
    "DE89 3704 0044 0532 0130 00",
    "FR14 2004 1010 0505 0001 3M02 606",
    "NL91 ABNA 0417 1643 00",
]
ROUTING_NUMBERS = ["021000021", "011000015", "122105278", "071000013"]
TICKET_CODES = ["ORD-2847293", "CLM-556789", "TK-445566", "FX987654321", "REQ-992814", "INC-420175"]
SUPPORT_EMAILS = [
    "support@servicehub.com",
    "helpdesk@company.com",
    "benefits@company.com",
    "customer.care@retailco.com",
    "privacy@enterprise.io",
]
SUPPORT_PHONES = ["(800) 555-0100", "(888) 555-0148", "(877) 555-0121", "(866) 555-0159"]
NOTIFICATION_DOMAINS = ["alerts.company.com", "portal.healthsystem.org", "access.enterprise.io"]


@dataclass
class FixturePerson:
    full_name: str
    personal_email: str
    work_email: str
    phone: str
    address: str
    dob_text: str
    ssn: str
    sin: str
    drivers_license: str
    passport: str
    mrn: str
    medicare: str
    npi: str
    bank_account: str
    routing_number: str
    credit_card: str
    iban: str
    ein: str
    vin: str
    ipv4: str
    diagnosis_code: str
    ndc_code: str


@dataclass
class AttachmentSpec:
    filename: str
    mime_type: str
    data: bytes


def _luhn_check_digit(number_without_check: str) -> str:
    digits = [int(char) for char in number_without_check]
    parity = (len(digits) + 1) % 2
    total = 0
    for index, digit in enumerate(digits):
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return str((10 - (total % 10)) % 10)


def _generate_valid_npi(rng: random.Random) -> str:
    base = "1" + "".join(str(rng.randint(0, 9)) for _ in range(8))
    check = _luhn_check_digit("80840" + base)
    return base + check


def _generate_ssn(rng: random.Random) -> str:
    area = rng.randint(100, 665)
    group = rng.randint(10, 99)
    serial = rng.randint(1000, 9999)
    return f"{area:03d}-{group:02d}-{serial:04d}"


def _generate_sin(rng: random.Random) -> str:
    base = "".join(str(rng.randint(1 if idx == 0 else 0, 9)) for idx in range(8))
    check = _luhn_check_digit(base)
    return f"{base[:3]} {base[3:6]} {base[6:8]}{check}"


def _generate_bank_account(rng: random.Random) -> str:
    return "".join(str(rng.randint(0, 9)) for _ in range(rng.randint(8, 12)))


def _generate_drivers_license(rng: random.Random) -> str:
    prefix = rng.choice(["CA", "TX", "OR", "AZ", "NC", "VA", "MN", "GA"])
    return f"{prefix}{rng.randint(1000000, 9999999)}"


def _generate_passport(rng: random.Random) -> str:
    letters = "ABCDEFGHJKLMNPRSTUVWXYZ"
    return rng.choice(letters) + "".join(str(rng.randint(0, 9)) for _ in range(8))


def _generate_mrn(rng: random.Random) -> str:
    return f"{rng.randint(100000, 999999)}"


def _generate_medicare(rng: random.Random) -> str:
    letters = "ACDEFGHJKLMNPQRTUVWXY"
    return (
        str(rng.randint(1, 9))
        + rng.choice(letters)
        + rng.choice(letters)
        + str(rng.randint(0, 9))
        + rng.choice(letters)
        + rng.choice(letters)
        + str(rng.randint(0, 9))
        + rng.choice(letters)
        + rng.choice(letters)
        + f"{rng.randint(0, 99):02d}"
    )


def _generate_ein(rng: random.Random) -> str:
    return f"{rng.randint(10, 98)}-{rng.randint(1000000, 9999999)}"


def _generate_vin(rng: random.Random) -> str:
    alphabet = "ABCDEFGHJKLMNPRSTUVWXYZ0123456789"
    return "".join(rng.choice(alphabet) for _ in range(17))


def _generate_ipv4(rng: random.Random) -> str:
    return f"{rng.randint(11, 198)}.{rng.randint(0, 255)}.{rng.randint(0, 255)}.{rng.randint(1, 254)}"


def _make_person(index: int, seed: int) -> FixturePerson:
    rng = random.Random(seed + index * 97)
    first_name = FIRST_NAMES[index % len(FIRST_NAMES)]
    last_name = LAST_NAMES[(index * 7) % len(LAST_NAMES)]
    city, state, postal = LOCATIONS[(index * 5) % len(LOCATIONS)]
    street_no = 100 + ((index * 37) % 8200)
    street = STREET_NAMES[(index * 11) % len(STREET_NAMES)]
    suffix = STREET_SUFFIXES[(index * 3) % len(STREET_SUFFIXES)]
    full_name = f"{first_name} {last_name}"
    personal_email = (
        f"{first_name.lower()}.{last_name.lower()}{index % 7 + 1}@"
        f"{CONSUMER_DOMAINS[index % len(CONSUMER_DOMAINS)]}"
    )
    work_email = f"{first_name.lower()}.{last_name.lower()}@{WORK_DOMAINS[index % len(WORK_DOMAINS)]}"
    phone = f"({rng.randint(212, 989)}) 555-{rng.randint(1000, 9999)}"
    address = f"{street_no} {street} {suffix}, {city}, {state} {postal}"
    dob_year = 1948 + ((index * 3) % 48)
    dob_month = rng.randint(1, 12)
    dob_day = rng.randint(1, 28)
    dob_text = f"{dob_month:02d}/{dob_day:02d}/{dob_year}"
    routing = ROUTING_NUMBERS[index % len(ROUTING_NUMBERS)]
    if not aba_check(routing):
        raise ValueError(f"Routing number {routing} did not pass checksum")

    return FixturePerson(
        full_name=full_name,
        personal_email=personal_email,
        work_email=work_email,
        phone=phone,
        address=address,
        dob_text=dob_text,
        ssn=_generate_ssn(rng),
        sin=_generate_sin(rng),
        drivers_license=_generate_drivers_license(rng),
        passport=_generate_passport(rng),
        mrn=_generate_mrn(rng),
        medicare=_generate_medicare(rng),
        npi=_generate_valid_npi(rng),
        bank_account=_generate_bank_account(rng),
        routing_number=routing,
        credit_card=TEST_CARD_NUMBERS[index % len(TEST_CARD_NUMBERS)],
        iban=IBAN_NUMBERS[index % len(IBAN_NUMBERS)],
        ein=_generate_ein(rng),
        vin=_generate_vin(rng),
        ipv4=_generate_ipv4(rng),
        diagnosis_code=DIAGNOSIS_CODES[index % len(DIAGNOSIS_CODES)],
        ndc_code=NDC_CODES[index % len(NDC_CODES)],
    )


def _business_noise(index: int) -> list[str]:
    return [
        f"Case reference: {TICKET_CODES[index % len(TICKET_CODES)]}",
        f"Support contact: {SUPPORT_EMAILS[index % len(SUPPORT_EMAILS)]}",
        f"Questions line: {SUPPORT_PHONES[index % len(SUPPORT_PHONES)]}",
        f"Follow-up due date: 2026-{(index % 9) + 1:02d}-{(index % 17) + 10:02d}",
    ]


def _field_lines(person: FixturePerson, bundle: list[str], index: int) -> tuple[list[str], list[tuple[str, str]]]:
    lines: list[str] = []
    findings: list[tuple[str, str]] = []

    for pii_type in bundle:
        if pii_type == "FULL_NAME":
            value = person.full_name
            lines.append(f"Full Name: {value}")
        elif pii_type == "DOB":
            value = person.dob_text
            label = "Date of Birth" if index % 2 == 0 else "DOB"
            lines.append(f"{label}: {value}")
        elif pii_type == "SSN":
            value = person.ssn
            lines.append(f"SSN: {value}")
        elif pii_type == "SIN":
            value = person.sin
            lines.append(f"SIN: {value}")
        elif pii_type == "EMAIL":
            value = person.personal_email
            lines.append(f"Personal Email: {value}")
        elif pii_type == "PHONE":
            value = person.phone
            lines.append(f"Mobile Phone: {value}")
        elif pii_type == "ADDRESS":
            value = person.address
            lines.append(f"Home Address: {value}")
        elif pii_type == "DRIVERS_LICENSE":
            value = person.drivers_license
            lines.append(f"Driver's License Number: {value}")
        elif pii_type == "PASSPORT":
            value = person.passport
            lines.append(f"Passport Number: {value}")
        elif pii_type == "MRN":
            value = person.mrn
            lines.append(f"MRN: {value}")
        elif pii_type == "MEDICARE":
            value = person.medicare
            lines.append(f"Medicare Number: {value}")
        elif pii_type == "NPI":
            value = person.npi
            lines.append(f"NPI: {value}")
        elif pii_type == "BANK_ACCOUNT":
            lines.append(f"Routing Number: {person.routing_number}")
            lines.append(f"Account Number: {person.bank_account}")
            findings.append(("BANK_ACCOUNT", person.routing_number))
            value = person.bank_account
        elif pii_type == "CREDIT_CARD":
            value = person.credit_card
            lines.append(f"Card Number: {value}")
        elif pii_type == "EIN":
            value = person.ein
            lines.append(f"EIN: {value}")
        elif pii_type == "IBAN":
            value = person.iban
            lines.append(f"IBAN: {value}")
        elif pii_type == "VIN":
            value = person.vin
            lines.append(f"VIN: {value}")
        elif pii_type == "ICD10":
            value = person.diagnosis_code
            lines.append(f"Diagnosis Code: {value}")
        elif pii_type == "NDC":
            value = person.ndc_code
            lines.append(f"NDC: {value}")
        elif pii_type == "IPV4":
            value = person.ipv4
            lines.append(f"Login IP Address: {value}")
        else:
            continue
        findings.append((pii_type, value))

    return lines, findings


def _field_pairs_for_attachment(person: FixturePerson, bundle: list[str], index: int) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for pii_type in bundle:
        if pii_type == "FULL_NAME":
            pairs.append(("Full Name", person.full_name))
        elif pii_type == "DOB":
            label = "Date of Birth" if index % 2 == 0 else "DOB"
            pairs.append((label, person.dob_text))
        elif pii_type == "SSN":
            pairs.append(("SSN", person.ssn))
        elif pii_type == "SIN":
            pairs.append(("SIN", person.sin))
        elif pii_type == "EMAIL":
            pairs.append(("Personal Email", person.personal_email))
        elif pii_type == "PHONE":
            pairs.append(("Mobile Phone", person.phone))
        elif pii_type == "ADDRESS":
            pairs.append(("Home Address", person.address))
        elif pii_type == "DRIVERS_LICENSE":
            pairs.append(("Drivers License Number", person.drivers_license))
        elif pii_type == "PASSPORT":
            pairs.append(("Passport Number", person.passport))
        elif pii_type == "MRN":
            pairs.append(("MRN", person.mrn))
        elif pii_type == "MEDICARE":
            pairs.append(("Medicare Number", person.medicare))
        elif pii_type == "NPI":
            pairs.append(("NPI", person.npi))
        elif pii_type == "BANK_ACCOUNT":
            pairs.append(("Routing Number", person.routing_number))
            pairs.append(("Account Number", person.bank_account))
        elif pii_type == "CREDIT_CARD":
            pairs.append(("Card Number", person.credit_card))
        elif pii_type == "EIN":
            pairs.append(("EIN", person.ein))
        elif pii_type == "IBAN":
            pairs.append(("IBAN", person.iban))
        elif pii_type == "VIN":
            pairs.append(("VIN", person.vin))
        elif pii_type == "ICD10":
            pairs.append(("Diagnosis Code", person.diagnosis_code))
        elif pii_type == "NDC":
            pairs.append(("NDC", person.ndc_code))
        elif pii_type == "IPV4":
            pairs.append(("Login IP Address", person.ipv4))
    return pairs


POSITIVE_BUNDLES = [
    ["FULL_NAME", "DOB", "PHONE", "ADDRESS"],
    ["FULL_NAME", "DOB", "SSN", "ADDRESS"],
    ["FULL_NAME", "DOB", "EMAIL", "PHONE"],
    ["FULL_NAME", "DOB", "DRIVERS_LICENSE", "PHONE"],
    ["FULL_NAME", "DOB", "PASSPORT", "EMAIL"],
    ["FULL_NAME", "MRN", "DOB", "PHONE"],
    ["FULL_NAME", "MEDICARE", "DOB", "ADDRESS"],
    ["FULL_NAME", "BANK_ACCOUNT", "DOB"],
    ["FULL_NAME", "CREDIT_CARD", "ADDRESS"],
    ["FULL_NAME", "EIN", "ADDRESS"],
    ["FULL_NAME", "IBAN", "ADDRESS"],
    ["FULL_NAME", "VIN", "ADDRESS"],
    ["FULL_NAME", "ICD10", "NDC", "DOB"],
    ["FULL_NAME", "NPI", "EMAIL", "PHONE"],
    ["FULL_NAME", "SIN", "DOB", "ADDRESS"],
    ["FULL_NAME", "IPV4", "EMAIL"],
]


ATTACHMENT_ROTATION = [
    "txt",
    "csv",
    "docx",
    "xlsx",
    "rtf",
]


def _negative_subject(index: int) -> str:
    subjects = [
        "Project Timeline Review",
        "Order Status Update",
        "Security Alert Digest",
        "Facilities Maintenance Window",
        "Benefits FAQ Refresh",
        "Quarterly Finance Checklist",
        "Training Schedule Reminder",
        "Contract Routing Update",
        "Travel Policy Notice",
        "Vendor Ticket Acknowledgment",
    ]
    return f"{subjects[index % len(subjects)]} #{TICKET_CODES[index % len(TICKET_CODES)]}"


def _negative_lines(index: int) -> list[str]:
    org = ORG_NAMES[index % len(ORG_NAMES)]
    return [
        f"{org} is sending an operational update for the upcoming workstream.",
        f"Ticket reference: {TICKET_CODES[index % len(TICKET_CODES)]}",
        f"Support inbox: {SUPPORT_EMAILS[index % len(SUPPORT_EMAILS)]}",
        f"Callback line: {SUPPORT_PHONES[index % len(SUPPORT_PHONES)]}",
        f"Review date: 2026-{(index % 9) + 1:02d}-{(index % 19) + 10:02d}",
        f"Source IP: 203.{index % 100}.{(index * 3) % 200}.{(index * 7) % 200 + 1}",
    ]


def _positive_subject(index: int, bundle: list[str]) -> str:
    if "MRN" in bundle or "MEDICARE" in bundle or "ICD10" in bundle:
        return "Patient Intake Packet Review"
    if "EIN" in bundle:
        return "Vendor Tax Documentation Review"
    if "BANK_ACCOUNT" in bundle or "CREDIT_CARD" in bundle or "IBAN" in bundle:
        return "Payment Exception Follow-up"
    if "NPI" in bundle:
        return "Provider Credential Verification"
    return "Record Verification Required"


def _positive_intro(index: int, person: FixturePerson) -> list[str]:
    org = ORG_NAMES[index % len(ORG_NAMES)]
    return [
        f"{org} requested a review of the enclosed record before release.",
        f"Internal ticket: {TICKET_CODES[index % len(TICKET_CODES)]}",
        *_business_noise(index),
        f"Assigned coordinator: {SUPPORT_EMAILS[(index + 1) % len(SUPPORT_EMAILS)]}",
        f"Record owner: {person.full_name}",
    ]
