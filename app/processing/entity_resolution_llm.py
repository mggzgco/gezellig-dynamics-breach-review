"""Local-LLM escalation for ambiguous attribution cases only."""

from __future__ import annotations

import re
from typing import Optional

from app.settings import (
    LOCAL_LLM_AMBIGUITY_MARGIN,
    LOCAL_LLM_MAX_CANDIDATES,
    LOCAL_LLM_MAX_REQUESTS_PER_EMAIL,
    LOCAL_LLM_TRIGGER_CONFIDENCE,
)
from app.models import EmailAnalysisResult, PIIMatch
from app.processing.entity_resolution_models import AttributionDecision, ResolverRuntimeState, ScoredCandidate, TextBlock
from app.processing.entity_resolution_utils import entity_key, entity_type_from_role, normalize_name
from app.processing.local_llm_attribution import (
    LLMAttributionCandidate,
    LLMAttributionRequest,
    LLMAttributionResponse,
    LocalLLMAttributionHelper,
)


def maybe_resolve_with_local_llm(
    *,
    match: PIIMatch,
    result: EmailAnalysisResult,
    block: TextBlock,
    blocks: list[TextBlock],
    block_index: Optional[int],
    scored_candidates: list[ScoredCandidate],
    deterministic_decision: Optional[AttributionDecision],
    direct_fallback: Optional[AttributionDecision],
    llm_helper: LocalLLMAttributionHelper,
    runtime_state: ResolverRuntimeState,
) -> Optional[AttributionDecision]:
    """Ask the local model to break ties only when deterministic logic is inconclusive."""
    if not should_consult_local_llm(scored_candidates, deterministic_decision, llm_helper, runtime_state):
        return None

    llm_candidates = build_llm_candidates(scored_candidates, direct_fallback)
    if len(llm_candidates) < 2:
        return None

    attribution_request = build_llm_request(match, block, blocks, block_index, llm_candidates)
    cache_key = (
        match.source_ref,
        normalize_text_for_cache(attribution_request.current_block),
        tuple(candidate.candidate_id for candidate in attribution_request.candidates),
    )
    if cache_key in runtime_state.llm_cache:
        return runtime_state.llm_cache[cache_key]

    if runtime_state.llm_calls >= LOCAL_LLM_MAX_REQUESTS_PER_EMAIL:
        runtime_state.llm_cache[cache_key] = None
        return None

    response = llm_helper.choose_candidate(attribution_request)
    runtime_state.llm_calls += 1
    llm_decision = decision_from_llm_response(
        response=response,
        llm_candidates=llm_candidates,
        deterministic_decision=deterministic_decision,
        match=match,
        result=result,
        block=block,
    )
    runtime_state.llm_cache[cache_key] = llm_decision
    return llm_decision


def should_consult_local_llm(
    scored_candidates: list[ScoredCandidate],
    deterministic_decision: Optional[AttributionDecision],
    llm_helper: LocalLLMAttributionHelper,
    runtime_state: ResolverRuntimeState,
) -> bool:
    """Return `True` only for genuinely ambiguous candidate sets."""
    if not llm_helper.enabled or runtime_state.llm_calls >= LOCAL_LLM_MAX_REQUESTS_PER_EMAIL:
        return False
    if not scored_candidates:
        return False

    top_candidates = sorted(scored_candidates, key=lambda candidate: candidate.score, reverse=True)
    if deterministic_decision and deterministic_decision.method in {"self_identifying_email", "self_identifying_name"}:
        return False
    if len(top_candidates) == 1 and top_candidates[0].score >= LOCAL_LLM_TRIGGER_CONFIDENCE:
        return False
    if deterministic_decision and deterministic_decision.confidence < LOCAL_LLM_TRIGGER_CONFIDENCE:
        return True
    if len(top_candidates) >= 2 and (top_candidates[0].score - top_candidates[1].score) <= LOCAL_LLM_AMBIGUITY_MARGIN:
        return True
    return False


def build_llm_candidates(
    scored_candidates: list[ScoredCandidate],
    direct_fallback: Optional[AttributionDecision],
) -> list[LLMAttributionCandidate]:
    """Convert internal scored candidates into the smaller LLM-facing schema."""
    llm_candidates: list[LLMAttributionCandidate] = []
    seen = set()

    sorted_candidates = sorted(
        scored_candidates,
        key=lambda candidate: (
            candidate.score,
            len(candidate.evidence),
            candidate.canonical_email or "",
            candidate.canonical_name or "",
        ),
        reverse=True,
    )

    for index, candidate in enumerate(sorted_candidates[:LOCAL_LLM_MAX_CANDIDATES], start=1):
        key = (candidate.canonical_email or "", normalize_name(candidate.canonical_name), candidate.role or "")
        if key in seen:
            continue
        seen.add(key)
        llm_candidates.append(
            LLMAttributionCandidate(
                candidate_id=f"C{index}",
                canonical_name=candidate.canonical_name,
                canonical_email=candidate.canonical_email,
                role=candidate.role,
                method=candidate.method,
                score=round(candidate.score, 2),
                evidence=list(candidate.evidence),
            )
        )

    if direct_fallback and len(llm_candidates) < LOCAL_LLM_MAX_CANDIDATES:
        fallback_key = (
            direct_fallback.canonical_email or "",
            normalize_name(direct_fallback.canonical_name),
            direct_fallback.entity_type,
        )
        if fallback_key not in seen:
            llm_candidates.append(
                LLMAttributionCandidate(
                    candidate_id=f"C{len(llm_candidates) + 1}",
                    canonical_name=direct_fallback.canonical_name,
                    canonical_email=direct_fallback.canonical_email,
                    role=direct_fallback.entity_type,
                    method=direct_fallback.method,
                    score=direct_fallback.confidence,
                    evidence=list(direct_fallback.evidence),
                )
            )

    return llm_candidates


def build_llm_request(
    match: PIIMatch,
    block: TextBlock,
    blocks: list[TextBlock],
    block_index: Optional[int],
    llm_candidates: list[LLMAttributionCandidate],
) -> LLMAttributionRequest:
    """Build the bounded local-LLM request payload around the current block."""
    previous_block = blocks[block_index - 1].text if block_index is not None and block_index > 0 else ""
    next_block = blocks[block_index + 1].text if block_index is not None and block_index + 1 < len(blocks) else ""
    return LLMAttributionRequest(
        source_ref=match.source_ref,
        pii_type=match.pii_type,
        redacted_value=match.redacted_value,
        finding_excerpt=match.excerpt,
        current_block=block.text,
        previous_block=previous_block,
        next_block=next_block,
        candidates=llm_candidates,
    )


def decision_from_llm_response(
    *,
    response: Optional[LLMAttributionResponse],
    llm_candidates: list[LLMAttributionCandidate],
    deterministic_decision: Optional[AttributionDecision],
    match: PIIMatch,
    result: EmailAnalysisResult,
    block: TextBlock,
) -> Optional[AttributionDecision]:
    """Validate the model choice and merge it back into an attribution decision."""
    if response is None:
        return None

    if response.candidate_id == "UNATTRIBUTED":
        if deterministic_decision and deterministic_decision.confidence >= LOCAL_LLM_TRIGGER_CONFIDENCE:
            return None
        return AttributionDecision(
            entity_key=f"unattributed:{result.eml_filename}:{match.source_ref}:{block.start}:{block.end}",
            canonical_name="UNATTRIBUTED",
            canonical_email=None,
            entity_type="UNATTRIBUTED_BLOCK",
            confidence=0.0,
            method="hybrid_local_llm_unattributed",
            evidence=[*response.evidence_quotes, f"llm_model={response.model}"],
        )

    candidate = next((item for item in llm_candidates if item.candidate_id == response.candidate_id), None)
    if not candidate:
        return None

    if (
        deterministic_decision
        and deterministic_decision.canonical_email == candidate.canonical_email
        and deterministic_decision.canonical_name == candidate.canonical_name
    ):
        combined_confidence = round(min(0.99, (candidate.score * 0.6) + (response.confidence * 0.4) + 0.03), 2)
    elif deterministic_decision and response.confidence < LOCAL_LLM_TRIGGER_CONFIDENCE:
        return None
    else:
        combined_confidence = round(min(0.99, (candidate.score * 0.55) + (response.confidence * 0.45) + 0.02), 2)

    entity_type = entity_type_from_role(candidate.role)
    evidence = list(candidate.evidence)
    for quote in response.evidence_quotes:
        if quote not in evidence:
            evidence.append(quote)
    evidence.append(f"llm_model={response.model}")
    evidence.append(f"llm_reason={response.reason}" if response.reason else "llm_reason=not_provided")

    return AttributionDecision(
        entity_key=entity_key(candidate.canonical_name, candidate.canonical_email, entity_type),
        canonical_name=candidate.canonical_name,
        canonical_email=candidate.canonical_email,
        entity_type=entity_type,
        confidence=combined_confidence,
        method="hybrid_local_llm",
        evidence=evidence,
    )


def normalize_text_for_cache(value: str) -> str:
    """Collapse whitespace and cap size so cache keys stay stable and bounded."""
    return re.sub(r"\s+", " ", value).strip().lower()[:600]
