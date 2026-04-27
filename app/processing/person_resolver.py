"""Backward-compatible person-resolution entrypoint."""

from typing import Optional

from app.models import EmailAnalysisResult, PersonRecord
from app.processing.entity_resolver import resolve_entities
from app.processing.local_llm_attribution import LocalLLMAttributionHelper


def resolve_persons(
    email_results: list[EmailAnalysisResult],
    llm_helper: Optional[LocalLLMAttributionHelper] = None,
) -> list[PersonRecord]:
    """
    Resolve content subject entities from analyzed email results.

    This replaces the old participant-level fanout model. Findings are first
    attributed to the best-supported subject entity from the content itself,
    and only then aggregated into person records.
    """
    return resolve_entities(email_results, llm_helper=llm_helper)
