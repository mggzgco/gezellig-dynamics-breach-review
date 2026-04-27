"""Compatibility facade for PII detection plumbing.

The concrete registry lives in `app.pii_catalog`. Shared helpers are split by
concern across normalization, validation, keyword compilation, match filters,
and pattern type definitions.
"""

from app.settings import CONTEXT_WINDOW_CHARS, REGEX_FLAGS
from app.pii_keywords import compile_keyword_patterns
from app.pii_match_filters import (
    _looks_generic_role_email,
    bank_account_match_filter,
    dob_match_filter,
    email_match_filter,
    ipv4_match_filter,
    phone_match_filter,
    ssn_match_filter,
)
from app.pii_normalization import (
    compact_alnum,
    digits_only,
    normalize_address,
    normalize_email,
    normalize_name,
    normalize_phone,
)
from app.pii_pattern_types import PIIPattern
from app.pii_validation import (
    aba_check,
    bank_account_check,
    dob_check,
    drivers_license_check,
    full_name_check,
    iban_check,
    luhn_check,
    mrn_check,
    normalize_dob,
    npi_check,
    passport_check,
    sin_check,
)

_compile_keyword_patterns = compile_keyword_patterns

__all__ = [
    "PIIPattern",
    "CONTEXT_WINDOW_CHARS",
    "REGEX_FLAGS",
    "compile_keyword_patterns",
    "_compile_keyword_patterns",
    "digits_only",
    "compact_alnum",
    "normalize_email",
    "normalize_phone",
    "normalize_address",
    "normalize_name",
    "normalize_dob",
    "luhn_check",
    "aba_check",
    "sin_check",
    "iban_check",
    "npi_check",
    "bank_account_check",
    "passport_check",
    "drivers_license_check",
    "mrn_check",
    "full_name_check",
    "dob_check",
    "dob_match_filter",
    "email_match_filter",
    "phone_match_filter",
    "ssn_match_filter",
    "bank_account_match_filter",
    "ipv4_match_filter",
    "_looks_generic_role_email",
]
