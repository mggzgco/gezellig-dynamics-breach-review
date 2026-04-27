"""Concrete ordered PII catalog.

The rule definitions are split by domain so the registry stays readable without
changing the public `app.pii_catalog` import surface.
"""

from __future__ import annotations

from app.pii_catalog_financial import (
    BANK_ACCOUNT_PATTERN,
    BANK_ROUTING_PATTERN,
    CREDIT_CARD_PATTERN,
    FINANCIAL_PATTERNS,
    IBAN_PATTERN,
)
from app.pii_catalog_government import (
    DRIVERS_LICENSE_PATTERN,
    EIN_PATTERN,
    GOVERNMENT_IDENTIFIER_PATTERNS,
    PASSPORT_PATTERN,
    SIN_PATTERN,
    SSN_PATTERN,
)
from app.pii_catalog_health import (
    HEALTH_PATTERNS,
    ICD10_PATTERN,
    MEDICARE_PATTERN,
    MRN_PATTERN,
    NDC_PATTERN,
    NPI_PATTERN,
)
from app.pii_catalog_personal import (
    ADDRESS_PATTERN,
    DOB_PATTERN,
    EMAIL_PATTERN,
    FULL_NAME_PATTERN,
    IPV4_PATTERN,
    PERSONAL_PATTERNS,
    PHONE_PATTERN,
    VIN_PATTERN,
    ZIP_PATTERN,
)

PII_CATALOG = [
    SSN_PATTERN,
    SIN_PATTERN,
    CREDIT_CARD_PATTERN,
    BANK_ROUTING_PATTERN,
    BANK_ACCOUNT_PATTERN,
    PASSPORT_PATTERN,
    DRIVERS_LICENSE_PATTERN,
    MEDICARE_PATTERN,
    MRN_PATTERN,
    NPI_PATTERN,
    IBAN_PATTERN,
    EIN_PATTERN,
    DOB_PATTERN,
    ADDRESS_PATTERN,
    FULL_NAME_PATTERN,
    ZIP_PATTERN,
    EMAIL_PATTERN,
    PHONE_PATTERN,
    VIN_PATTERN,
    ICD10_PATTERN,
    NDC_PATTERN,
    IPV4_PATTERN,
]

DOMAIN_PATTERN_GROUPS = {
    "government_identifier": GOVERNMENT_IDENTIFIER_PATTERNS,
    "financial": FINANCIAL_PATTERNS,
    "health": HEALTH_PATTERNS,
    "personal": PERSONAL_PATTERNS,
}

__all__ = [
    "SSN_PATTERN",
    "SIN_PATTERN",
    "CREDIT_CARD_PATTERN",
    "BANK_ROUTING_PATTERN",
    "BANK_ACCOUNT_PATTERN",
    "PASSPORT_PATTERN",
    "DRIVERS_LICENSE_PATTERN",
    "MEDICARE_PATTERN",
    "MRN_PATTERN",
    "NPI_PATTERN",
    "IBAN_PATTERN",
    "EIN_PATTERN",
    "DOB_PATTERN",
    "ADDRESS_PATTERN",
    "FULL_NAME_PATTERN",
    "ZIP_PATTERN",
    "EMAIL_PATTERN",
    "PHONE_PATTERN",
    "VIN_PATTERN",
    "ICD10_PATTERN",
    "NDC_PATTERN",
    "IPV4_PATTERN",
    "DOMAIN_PATTERN_GROUPS",
    "PII_CATALOG",
]
