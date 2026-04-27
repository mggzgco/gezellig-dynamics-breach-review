"""Deterministic finding-to-entity attribution logic.

This module answers the primary ownership question using content-first rules.
The local model is only consulted after these heuristics produce an ambiguous
candidate set.
"""

from __future__ import annotations

from app.models import EmailAnalysisResult, PIIMatch
from app.processing.entity_resolution_extraction import (
    build_blocks,
    extract_mentions,
    find_block_index,
    neighbor_mentions,
)
from app.processing.entity_resolution_fallbacks import direct_notice_fallback, self_identifying_fallback
from app.processing.entity_resolution_llm import maybe_resolve_with_local_llm
from app.processing.entity_resolution_models import (
    AttributionDecision,
    ResolverRuntimeState,
    TextBlock,
)
from app.processing.entity_resolution_scoring import decision_from_candidates, score_candidates
from app.processing.entity_resolution_utils import (
    entity_key,
)
from app.processing.local_llm_attribution import LocalLLMAttributionHelper


def attribute_match(
    match: PIIMatch,
    result: EmailAnalysisResult,
    participants,
    source_blocks: dict[str, list[TextBlock]],
    llm_helper: LocalLLMAttributionHelper,
    runtime_state: ResolverRuntimeState,
) -> AttributionDecision:
    """Resolve one finding to the best-supported subject entity."""
    source_text = result.source_texts.get(match.source_ref, "")
    blocks = source_blocks.get(match.source_ref, [])
    block_index = find_block_index(blocks, match.char_offset)
    block = blocks[block_index] if block_index is not None else TextBlock(match.source_ref, 0, len(source_text), source_text)

    current_mentions = extract_mentions(block.text, participants)
    nearby_mentions = neighbor_mentions(blocks, block_index, participants) if block_index is not None else []
    scored_candidates = score_candidates(match, current_mentions + nearby_mentions, participants)
    deterministic_decision = decision_from_candidates(scored_candidates, participants)
    direct_fallback = direct_notice_fallback(match, source_text, blocks, block_index, result, participants)

    llm_decision = maybe_resolve_with_local_llm(
        match=match,
        result=result,
        block=block,
        blocks=blocks,
        block_index=block_index,
        scored_candidates=scored_candidates,
        deterministic_decision=deterministic_decision,
        direct_fallback=direct_fallback,
        llm_helper=llm_helper,
        runtime_state=runtime_state,
    )
    if llm_decision:
        return llm_decision
    if deterministic_decision:
        return deterministic_decision
    if direct_fallback:
        return direct_fallback

    self_identified = self_identifying_fallback(match)
    if self_identified:
        return self_identified

    unattributed_key = f"unattributed:{result.eml_filename}:{match.source_ref}:{block.start}:{block.end}"
    return AttributionDecision(
        entity_key=unattributed_key,
        canonical_name="UNATTRIBUTED",
        canonical_email=None,
        entity_type="UNATTRIBUTED_BLOCK",
        confidence=0.0,
        method="unattributed_block",
        evidence=[f"source={match.source_ref}", f"block={block.start}-{block.end}"],
    )


def build_source_blocks(result: EmailAnalysisResult) -> dict[str, list[TextBlock]]:
    """Pre-segment each source text into stable block units for attribution."""
    return {
        source_ref: build_blocks(source_ref, text)
        for source_ref, text in result.source_texts.items()
        if text
    }
