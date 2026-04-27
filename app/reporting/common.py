from app.runtime_metadata import CURRENT_BUILD_ID, CURRENT_BUILD_LABEL, utc_timestamp

PII_DISPLAY_LABELS = {
    "SSN": "Social Security Number",
    "SIN": "Canadian Social Insurance Number",
    "CREDIT_CARD": "Payment Card",
    "BANK_ACCOUNT": "Bank Account",
    "PASSPORT": "Passport",
    "DRIVERS_LICENSE": "Driver's License",
    "MEDICARE": "Medicare ID",
    "MRN": "Medical Record Number",
    "NPI": "National Provider Identifier",
    "IBAN": "IBAN",
    "EIN": "Employer ID Number",
    "EMAIL": "Email Address",
    "PHONE": "Phone Number",
    "DOB": "Date of Birth",
    "FULL_NAME": "Full Name",
    "ADDRESS": "Street Address",
    "ZIP": "ZIP / Postal Code",
    "VIN": "Vehicle ID Number",
    "ICD10": "ICD-10 Code",
    "NDC": "Drug Code",
    "IPV4": "IP Address",
}

RISK_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "NONE": 4}


def humanize_pii(pii_type: str) -> str:
    return PII_DISPLAY_LABELS.get(pii_type, pii_type.replace("_", " ").title())


def source_email_file(source_ref: str) -> str:
    if " > " in source_ref:
        return source_ref.split(" > ", 1)[0].strip()
    if " (" in source_ref:
        return source_ref.split(" (", 1)[0].strip()
    return source_ref.strip()


def build_report_metadata(schema_version: str) -> dict[str, str]:
    return {
        "report_schema_version": schema_version,
        "report_build_id": CURRENT_BUILD_ID,
        "report_generated_utc": utc_timestamp(),
        "report_build_label": CURRENT_BUILD_LABEL,
    }
