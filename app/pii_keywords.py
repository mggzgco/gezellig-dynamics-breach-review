from __future__ import annotations

import re

from app.settings import REGEX_FLAGS


def compile_keyword_patterns(keywords: list[str]) -> list[re.Pattern]:
    patterns = []
    for keyword in keywords:
        escaped = re.escape(keyword.strip()).replace(r"\ ", r"\s+")
        patterns.append(re.compile(rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])", REGEX_FLAGS))
    return patterns
