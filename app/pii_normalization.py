from __future__ import annotations

import re


def digits_only(value: str) -> str:
    return re.sub(r"\D", "", value)


def compact_alnum(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", value).upper()


def normalize_email(value: str) -> str:
    return value.strip().lower()


def normalize_phone(value: str) -> str:
    digits = digits_only(value)
    if len(digits) >= 11 and digits.startswith("1"):
        return digits[1:11]
    if len(digits) >= 10:
        return digits[:10]
    return digits


def normalize_address(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().upper()


def normalize_name(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().upper()
