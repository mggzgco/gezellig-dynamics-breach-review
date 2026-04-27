"""Financial identifier detection rules."""

from __future__ import annotations

import re

from app.pii_match_filter_sensitive import bank_account_match_filter
from app.pii_normalization import compact_alnum, digits_only
from app.pii_pattern_types import PIIPattern
from app.pii_validation import aba_check, bank_account_check, iban_check, luhn_check
from app.settings import CONTEXT_WINDOW_CHARS, REGEX_FLAGS

CREDIT_CARD_PATTERN = PIIPattern(
    name="CREDIT_CARD",
    category="financial",
    subtype="payment_card_number",
    patterns=[re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)", REGEX_FLAGS)],
    risk_level="HIGH",
    requires_context=False,
    context_keywords=["card", "credit", "debit", "visa", "mastercard", "amex", "discover", "payment"],
    strong_context_keywords=["card number", "credit card", "debit card"],
    negative_keywords=["order number", "invoice number", "confirmation number"],
    context_window=CONTEXT_WINDOW_CHARS,
    hipaa=False,
    ccpa=True,
    pipeda=True,
    notification_required=True,
    validator=luhn_check,
    normalizer=digits_only,
    base_confidence=0.84,
    min_confidence=0.8,
    detection_method="regex+checksum",
    priority=98,
)

BANK_ROUTING_PATTERN = PIIPattern(
    name="BANK_ACCOUNT",
    category="financial",
    subtype="routing_number",
    patterns=[
        re.compile(
            r"\b(?:routing|aba|transit)(?:\s+(?:number|no\.?|#))?[\s#:.,-]*([0-9]{9})\b",
            REGEX_FLAGS,
        )
    ],
    risk_level="HIGH",
    requires_context=False,
    context_keywords=["routing", "aba", "transit", "bank", "ach"],
    strong_context_keywords=["routing number", "aba", "transit number"],
    context_window=150,
    hipaa=False,
    ccpa=True,
    pipeda=True,
    notification_required=True,
    validator=aba_check,
    normalizer=digits_only,
    match_group=1,
    base_confidence=0.91,
    min_confidence=0.88,
    detection_method="regex+label+checksum",
    priority=97,
)

BANK_ACCOUNT_PATTERN = PIIPattern(
    name="BANK_ACCOUNT",
    category="financial",
    subtype="account_number",
    patterns=[
        re.compile(
            r"\b(?:bank\s+account|account|acct|checking|savings)(?:\s+(?:number|no\.?|#))?[\s#:.,-]*([0-9][0-9 -]{5,24}[0-9])\b",
            REGEX_FLAGS,
        )
    ],
    risk_level="HIGH",
    requires_context=False,
    context_keywords=["account", "acct", "bank", "checking", "savings"],
    strong_context_keywords=["account number", "acct #", "bank account"],
    negative_keywords=["order number", "invoice number", "confirmation number"],
    context_window=150,
    hipaa=False,
    ccpa=True,
    pipeda=True,
    notification_required=True,
    validator=bank_account_check,
    match_filter=bank_account_match_filter,
    normalizer=digits_only,
    match_group=1,
    base_confidence=0.86,
    min_confidence=0.84,
    detection_method="regex+label",
    priority=96,
)

IBAN_PATTERN = PIIPattern(
    name="IBAN",
    category="financial",
    subtype="international_bank_account_number",
    patterns=[re.compile(r"\b[A-Z]{2}\d{2}(?:[ -]?[A-Z0-9]{2,4}){3,8}\b", REGEX_FLAGS)],
    risk_level="MEDIUM",
    requires_context=False,
    context_keywords=["iban", "account", "bank", "wire", "transfer"],
    strong_context_keywords=["iban", "international bank account"],
    context_window=CONTEXT_WINDOW_CHARS,
    hipaa=False,
    ccpa=True,
    pipeda=True,
    notification_required=False,
    validator=iban_check,
    normalizer=compact_alnum,
    base_confidence=0.88,
    min_confidence=0.86,
    detection_method="regex+checksum",
    priority=90,
)

FINANCIAL_PATTERNS = (
    CREDIT_CARD_PATTERN,
    BANK_ROUTING_PATTERN,
    BANK_ACCOUNT_PATTERN,
    IBAN_PATTERN,
)
