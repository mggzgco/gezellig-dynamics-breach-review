from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Optional

from app.pii_keywords import compile_keyword_patterns


@dataclass
class PIIPattern:
    name: str
    category: str
    subtype: str
    patterns: list[re.Pattern]
    risk_level: str
    requires_context: bool
    context_keywords: list[str]
    context_window: int
    hipaa: bool
    ccpa: bool
    pipeda: bool
    notification_required: bool
    strong_context_keywords: list[str] = field(default_factory=list)
    negative_keywords: list[str] = field(default_factory=list)
    validator: Optional[Callable[[str], bool]] = None
    match_filter: Optional[Callable[[str, str, int, int, str, str, str], bool]] = None
    normalizer: Optional[Callable[[str], str]] = None
    match_group: int = 0
    base_confidence: float = 0.7
    min_confidence: float = 0.7
    detection_method: str = "regex"
    priority: int = 50
    context_patterns: list[re.Pattern] = field(init=False, repr=False)
    strong_context_patterns: list[re.Pattern] = field(init=False, repr=False)
    negative_context_patterns: list[re.Pattern] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.context_patterns = compile_keyword_patterns(self.context_keywords)
        self.strong_context_patterns = compile_keyword_patterns(self.strong_context_keywords)
        self.negative_context_patterns = compile_keyword_patterns(self.negative_keywords)
