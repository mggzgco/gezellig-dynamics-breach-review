from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class HeaderParticipant:
    email: str
    name: Optional[str]
    role: str


@dataclass
class TextBlock:
    source_ref: str
    start: int
    end: int
    text: str


@dataclass
class EntityMention:
    name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    confidence: float = 0.0
    method: str = ""
    evidence: list[str] = field(default_factory=list)
    same_block: bool = True


@dataclass
class AttributionDecision:
    entity_key: str
    canonical_name: Optional[str]
    canonical_email: Optional[str]
    entity_type: str
    confidence: float
    method: str
    evidence: list[str]


@dataclass
class ScoredCandidate:
    canonical_name: Optional[str]
    canonical_email: Optional[str]
    role: Optional[str]
    score: float
    method: str
    evidence: list[str]
    same_block: bool


@dataclass
class ResolverRuntimeState:
    llm_cache: dict[tuple[str, str, tuple[str, ...]], Optional[AttributionDecision]] = field(
        default_factory=dict
    )
    llm_calls: int = 0
