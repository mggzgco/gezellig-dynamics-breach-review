import logging
import re
from dataclasses import dataclass
from typing import Optional
import json

from app.settings import (
    LOCAL_LLM_ACCEPT_CONFIDENCE,
    LOCAL_LLM_BASE_URL,
    LOCAL_LLM_ENABLED,
    LOCAL_LLM_MAX_CONTEXT_CHARS,
    LOCAL_LLM_MODEL,
    LOCAL_LLM_PROVIDER,
    LOCAL_LLM_TIMEOUT_SECONDS,
)
from app.processing.local_llm_common import StructuredObjectParser, request_json

logger = logging.getLogger(__name__)


@dataclass
class LLMAttributionCandidate:
    candidate_id: str
    canonical_name: Optional[str]
    canonical_email: Optional[str]
    role: Optional[str]
    method: str
    score: float
    evidence: list[str]


@dataclass
class LLMAttributionRequest:
    source_ref: str
    pii_type: str
    redacted_value: str
    finding_excerpt: str
    current_block: str
    previous_block: str
    next_block: str
    candidates: list[LLMAttributionCandidate]


@dataclass
class LLMAttributionResponse:
    candidate_id: str
    confidence: float
    evidence_quotes: list[str]
    reason: str
    model: str
    raw_response: str


class LocalLLMAttributionHelper:
    def __init__(
        self,
        *,
        enabled: bool = LOCAL_LLM_ENABLED,
        provider: str = LOCAL_LLM_PROVIDER,
        model: str = LOCAL_LLM_MODEL,
        base_url: str = LOCAL_LLM_BASE_URL,
        timeout_seconds: float = LOCAL_LLM_TIMEOUT_SECONDS,
        accept_confidence: float = LOCAL_LLM_ACCEPT_CONFIDENCE,
        max_context_chars: int = LOCAL_LLM_MAX_CONTEXT_CHARS,
    ) -> None:
        self.enabled = enabled
        self.provider = provider
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.accept_confidence = accept_confidence
        self.max_context_chars = max_context_chars
        self._available = True

    def describe(self) -> str:
        state = "enabled" if self.enabled else "disabled"
        return f"{state}; provider={self.provider}; model={self.model}; base_url={self.base_url}"

    def probe(self) -> tuple[bool, str]:
        if not self.enabled:
            return False, "Local LLM attribution is disabled. Set PII_LOCAL_LLM_ENABLED=1 to enable it."
        if self.provider != "ollama":
            return False, f"Unsupported local LLM provider: {self.provider}"

        try:
            payload = self._request_json("/api/tags", method="GET")
        except Exception as exc:  # pragma: no cover - exercised through choose_candidate fallback
            self._available = False
            return False, f"Could not reach Ollama at {self.base_url}: {exc}"

        model_names = sorted(model.get("name", "") for model in payload.get("models", []) if model.get("name"))
        if self.model not in model_names:
            return False, (
                f"Ollama is reachable, but model '{self.model}' is not installed. "
                f"Installed models: {', '.join(model_names) if model_names else 'none'}"
            )

        return True, f"Ollama is reachable and model '{self.model}' is installed."

    def choose_candidate(self, attribution_request: LLMAttributionRequest) -> Optional[LLMAttributionResponse]:
        if not self.enabled or not self._available:
            return None
        if self.provider != "ollama":
            logger.warning("Skipping local LLM attribution because provider '%s' is unsupported", self.provider)
            self._available = False
            return None

        prompt = self._build_prompt(attribution_request)
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "think": False,
            "format": {
                "type": "object",
                "properties": {
                    "candidate_id": {"type": "string"},
                    "confidence": {"type": "number"},
                    "evidence_quotes": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "reason": {"type": "string"},
                },
                "required": ["candidate_id", "confidence", "evidence_quotes", "reason"],
            },
            "options": {
                "temperature": 0,
                "top_p": 0.1,
                "num_predict": 160,
            },
        }

        try:
            response_payload = self._request_json("/api/generate", payload=payload, method="POST")
        except Exception as exc:
            logger.warning("Local LLM attribution request failed: %s", exc)
            self._available = False
            return None

        raw_text = str(response_payload.get("response", "")).strip()
        parsed = self._extract_response_object(raw_text)
        if not parsed:
            logger.warning("Local LLM attribution returned unparsable output for %s", attribution_request.source_ref)
            return None

        return self._validate_response(attribution_request, parsed, raw_text)

    def _build_prompt(self, attribution_request: LLMAttributionRequest) -> str:
        candidate_payload = [
            {
                "candidate_id": candidate.candidate_id,
                "canonical_name": candidate.canonical_name,
                "canonical_email": candidate.canonical_email,
                "role": candidate.role,
                "anchor_method": candidate.method,
                "deterministic_score": candidate.score,
            }
            for candidate in attribution_request.candidates
        ]

        context_payload = {
            "source_ref": attribution_request.source_ref,
            "pii_type": attribution_request.pii_type,
            "redacted_value": attribution_request.redacted_value,
            "finding_excerpt": attribution_request.finding_excerpt,
            "previous_block": self._trim(attribution_request.previous_block),
            "current_block": self._trim(attribution_request.current_block),
            "next_block": self._trim(attribution_request.next_block),
            "candidates": candidate_payload,
        }

        instructions = (
            "You are helping with entity attribution for leaked PII. "
            "Choose exactly one candidate_id from the candidate list or choose UNATTRIBUTED. "
            "Use only the supplied context. Do not invent names or emails. "
            "Prefer UNATTRIBUTED if the owner is not explicit. "
            "Evidence quotes must be exact substrings copied from the context. "
            "Return only one JSON object with keys: candidate_id, confidence, evidence_quotes, reason."
        )

        return f"{instructions}\n\nContext JSON:\n{json.dumps(context_payload, ensure_ascii=True, indent=2)}"

    def _validate_response(
        self,
        attribution_request: LLMAttributionRequest,
        parsed: dict,
        raw_text: str,
    ) -> Optional[LLMAttributionResponse]:
        candidate_id = str(parsed.get("candidate_id", "")).strip()
        allowed_candidate_ids = {candidate.candidate_id for candidate in attribution_request.candidates}
        if candidate_id not in allowed_candidate_ids and candidate_id != "UNATTRIBUTED":
            return None

        try:
            confidence = float(parsed.get("confidence", 0.0))
        except (TypeError, ValueError):
            return None

        if confidence < 0 or confidence > 1:
            return None

        evidence_quotes = []
        raw_quotes = parsed.get("evidence_quotes", [])
        if isinstance(raw_quotes, list):
            for raw_quote in raw_quotes[:2]:
                if not isinstance(raw_quote, str):
                    continue
                cleaned_quote = raw_quote.strip().strip('"')
                if 4 <= len(cleaned_quote) <= 180 and self._quote_in_context(cleaned_quote, attribution_request):
                    evidence_quotes.append(cleaned_quote)

        if not evidence_quotes:
            return None

        reason = str(parsed.get("reason", "")).strip()
        if candidate_id != "UNATTRIBUTED" and confidence < self.accept_confidence:
            return None

        return LLMAttributionResponse(
            candidate_id=candidate_id,
            confidence=round(confidence, 2),
            evidence_quotes=evidence_quotes,
            reason=reason[:280],
            model=self.model,
            raw_response=raw_text[:1200],
        )

    def _quote_in_context(self, quote: str, attribution_request: LLMAttributionRequest) -> bool:
        haystack = "\n".join(
            part
            for part in (
                attribution_request.previous_block,
                attribution_request.current_block,
                attribution_request.next_block,
                attribution_request.finding_excerpt,
            )
            if part
        )
        return self._normalize_text(quote) in self._normalize_text(haystack)

    def _request_json(self, path: str, payload: Optional[dict] = None, method: str = "POST") -> dict:
        return request_json(self.base_url, self.timeout_seconds, path, payload=payload, method=method)

    def _extract_response_object(self, raw_text: str) -> Optional[dict]:
        return StructuredObjectParser.extract_response_object(raw_text)

    def _extract_first_json_object(self, raw_text: str) -> Optional[str]:
        return StructuredObjectParser.extract_first_json_object(raw_text)

    def _parse_dict_like_text(self, raw_text: Optional[str]) -> Optional[dict]:
        return StructuredObjectParser.parse_dict_like_text(raw_text)

    def _strip_code_fences(self, raw_text: str) -> str:
        return StructuredObjectParser.strip_code_fences(raw_text)

    def _clean_json_text(self, raw_text: str) -> str:
        return StructuredObjectParser.clean_json_text(raw_text)

    def _trim(self, text: str) -> str:
        text = text.strip()
        return text[: self.max_context_chars]

    def _normalize_text(self, value: str) -> str:
        return re.sub(r"\s+", " ", value).strip().lower()
