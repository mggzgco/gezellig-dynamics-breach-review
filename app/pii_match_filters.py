"""Compatibility facade for type-specific PII match filters."""

from app.pii_match_filter_personal import (
    dob_match_filter,
    email_match_filter,
    ipv4_match_filter,
    looks_generic_role_email as _looks_generic_role_email,
    phone_match_filter,
)
from app.pii_match_filter_sensitive import (
    bank_account_match_filter,
    ssn_match_filter,
)

__all__ = [
    "dob_match_filter",
    "email_match_filter",
    "phone_match_filter",
    "ssn_match_filter",
    "bank_account_match_filter",
    "ipv4_match_filter",
    "_looks_generic_role_email",
]
