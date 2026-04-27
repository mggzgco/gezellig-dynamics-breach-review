"""Structured local-LLM QA pass over file-level deterministic outcomes."""

import logging
import threading
from typing import Optional

from app.pii_catalog import PII_CATALOG
from app.settings import (
    LOCAL_LLM_BASE_URL,
    LOCAL_LLM_FILE_QA_ACCEPT_CONFIDENCE,
    LOCAL_LLM_FILE_QA_ENABLED,
    LOCAL_LLM_FILE_QA_KEEP_ALIVE,
    LOCAL_LLM_FILE_QA_MAX_CONTEXT_CHARS,
    LOCAL_LLM_FILE_QA_NUM_PREDICT,
    LOCAL_LLM_FILE_QA_REVIEW_ALL,
    LOCAL_LLM_FILE_QA_TIMEOUT_SECONDS,
    LOCAL_LLM_MODEL,
    LOCAL_LLM_PROVIDER,
)
from app.models import EmailAnalysisResult, FileQAReview
from app.processing.local_llm_common import request_json
from app.processing.local_llm_file_qa_parsing import extract_response_object
from app.processing.local_llm_file_qa_policy import (
    has_record_like_attachment,
    has_uncertain_extraction,
    needs_policy_review,
    policy_review_reason,
    should_review_result,
    uncertain_extraction_refs,
)
from app.processing.local_llm_file_qa_prompt import build_file_qa_prompt, normalize_text

logger = logging.getLogger(__name__)

KNOWN_PII_TYPES = {pattern.name for pattern in PII_CATALOG}


class LocalLLMFileQAHelper:
    """Structured QA review over deterministic file-level outcomes."""

    def __init__(
        self,
        *,
        enabled: bool = LOCAL_LLM_FILE_QA_ENABLED,
        provider: str = LOCAL_LLM_PROVIDER,
        model: str = LOCAL_LLM_MODEL,
        base_url: str = LOCAL_LLM_BASE_URL,
        timeout_seconds: float = LOCAL_LLM_FILE_QA_TIMEOUT_SECONDS,
        max_context_chars: int = LOCAL_LLM_FILE_QA_MAX_CONTEXT_CHARS,
        num_predict: int = LOCAL_LLM_FILE_QA_NUM_PREDICT,
        accept_confidence: float = LOCAL_LLM_FILE_QA_ACCEPT_CONFIDENCE,
        review_all_files: bool = LOCAL_LLM_FILE_QA_REVIEW_ALL,
        keep_alive: str = LOCAL_LLM_FILE_QA_KEEP_ALIVE,
    ) -> None:
        self.enabled = enabled
        self.provider = provider
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_context_chars = max_context_chars
        self.num_predict = num_predict
        self.accept_confidence = accept_confidence
        self.review_all_files = review_all_files
        self.keep_alive = keep_alive
        self._available = True
        self._availability_lock = threading.Lock()

    def review_email_result(self, result: EmailAnalysisResult) -> FileQAReview:
        if not self.enabled:
            return FileQAReview()
        if not should_review_result(result, review_all_files=self.review_all_files):
            return FileQAReview()
        if not self._is_available():
            return FileQAReview(
                reviewed=False,
                used_model=False,
                status="error",
                needs_human_review=True,
                reason="Local AI QA was unavailable for this file.",
                model=self.model,
                error="local_ai_qa_unavailable",
            )
        if self.provider != "ollama":
            return FileQAReview(status="error", needs_human_review=True, error=f"Unsupported provider: {self.provider}")

        prompt = self._build_prompt(result)
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "think": False,
            "keep_alive": self.keep_alive,
            "format": {
                "type": "object",
                "properties": {
                    "needs_human_review": {"type": "boolean"},
                    "confidence": {"type": "number"},
                    "suspected_missing_types": {"type": "array", "items": {"type": "string"}},
                    "questionable_detected_types": {"type": "array", "items": {"type": "string"}},
                    "evidence_quotes": {"type": "array", "items": {"type": "string"}},
                    "reason": {"type": "string"},
                },
                "required": [
                    "needs_human_review",
                    "confidence",
                    "suspected_missing_types",
                    "questionable_detected_types",
                    "evidence_quotes",
                    "reason",
                ],
            },
            "options": {
                "temperature": 0,
                "top_p": 0.1,
                "num_predict": self.num_predict,
            },
        }

        try:
            response_payload = self._request_json("/api/generate", payload=payload, method="POST")
        except Exception as exc:
            logger.warning("Local file QA request failed for %s: %s", result.eml_filename, exc)
            self._mark_unavailable()
            return FileQAReview(
                reviewed=False,
                used_model=False,
                status="error",
                needs_human_review=True,
                reason="Local AI QA was unavailable for this file.",
                model=self.model,
                error=str(exc),
            )

        raw_text = str(response_payload.get("response", "")).strip()
        parsed = extract_response_object(raw_text, self._clean_type_list)
        if not parsed:
            review = FileQAReview(
                reviewed=True,
                used_model=True,
                status="needs_review",
                needs_human_review=True,
                reason="Local AI QA returned output that could not be normalized into the required schema.",
                model=self.model,
                error=raw_text[:400],
            )
            return self._apply_review_guards(review, result)

        return self._apply_review_guards(self._validate_review(parsed, raw_text, result), result)

    def _build_prompt(self, result: EmailAnalysisResult) -> str:
        """Build a bounded QA prompt around deterministic findings and nearby context."""
        return build_file_qa_prompt(
            result,
            known_pii_types=KNOWN_PII_TYPES,
            max_context_chars=self.max_context_chars,
        )

    def _validate_review(self, parsed: dict, raw_text: str, result: EmailAnalysisResult) -> FileQAReview:
        """Normalize one parsed model response into the stable FileQAReview shape."""
        try:
            confidence = float(parsed.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))

        needs_human_review = bool(parsed.get("needs_human_review", False))
        missing_types = self._clean_type_list(parsed.get("suspected_missing_types", []))
        questionable_types = self._clean_type_list(parsed.get("questionable_detected_types", []))

        evidence_quotes = []
        raw_quotes = parsed.get("evidence_quotes", [])
        if isinstance(raw_quotes, list):
            for raw_quote in raw_quotes[:4]:
                if not isinstance(raw_quote, str):
                    continue
                cleaned = raw_quote.strip().strip('"')
                if 4 <= len(cleaned) <= 200 and self._quote_in_result(cleaned, result):
                    evidence_quotes.append(cleaned)

        reason = str(parsed.get("reason", "")).strip()[:320]
        if not reason:
            reason = "No reason provided."

        if confidence < self.accept_confidence and not needs_human_review:
            needs_human_review = True
            questionable_types = sorted(set(questionable_types))
            reason = "AI QA was not confident enough to clear this file automatically."

        status = "needs_review" if needs_human_review else "clear"
        if not evidence_quotes and needs_human_review:
            evidence_quotes = [result.subject or result.eml_filename]

        return FileQAReview(
            reviewed=True,
            used_model=True,
            status=status,
            needs_human_review=needs_human_review,
            confidence=round(confidence, 2),
            suspected_missing_types=missing_types,
            questionable_detected_types=questionable_types,
            evidence_quotes=evidence_quotes,
            reason=reason,
            model=self.model,
            error=None,
        )

    def _apply_review_guards(self, review: FileQAReview, result: EmailAnalysisResult) -> FileQAReview:
        """Prevent unsafe auto-clears when extraction quality is uncertain."""
        if review.status == "clear" and not result.pii_matches and has_record_like_attachment(result):
            review.status = "needs_review"
            review.needs_human_review = True
            review.confidence = min(review.confidence, 0.4)
            review.reason = "Record-like attachment had no deterministic findings; human review is required."
            review.error = review.error or "record_attachment_zero_findings"
            if not review.evidence_quotes:
                review.evidence_quotes = [result.subject or result.eml_filename]
        elif review.status == "clear" and needs_policy_review(result):
            review.status = "needs_review"
            review.needs_human_review = True
            review.confidence = min(review.confidence, 0.55)
            review.reason = policy_review_reason(result)
            review.error = review.error or "policy_review_required"
            if not review.evidence_quotes:
                review.evidence_quotes = [result.subject or result.eml_filename]
        elif review.status == "clear" and has_uncertain_extraction(result):
            review.status = "needs_review"
            review.needs_human_review = True
            review.confidence = min(review.confidence, 0.45)
            review.reason = "Extraction quality was uncertain due to OCR/layout confidence; human review is required."
            review.error = review.error or "uncertain_extraction_quality"
            if not review.evidence_quotes:
                review.evidence_quotes = uncertain_extraction_refs(result)
        return review

    def _clean_type_list(self, values: object) -> list[str]:
        cleaned: list[str] = []
        if not isinstance(values, list):
            return cleaned
        for value in values:
            if not isinstance(value, str):
                continue
            normalized = value.strip().upper()
            if normalized in KNOWN_PII_TYPES and normalized not in cleaned:
                cleaned.append(normalized)
        return cleaned

    def _quote_in_result(self, quote: str, result: EmailAnalysisResult) -> bool:
        haystack = "\n".join([result.subject or "", *result.source_texts.values()])
        return normalize_text(quote) in normalize_text(haystack)

    def _request_json(self, path: str, payload: Optional[dict] = None, method: str = "POST") -> dict:
        return request_json(self.base_url, self.timeout_seconds, path, payload=payload, method=method)

    def _extract_response_object(self, raw_text: str) -> Optional[dict]:
        """Compatibility wrapper for tests and any legacy private call sites."""
        return extract_response_object(raw_text, self._clean_type_list)

    def _is_available(self) -> bool:
        with self._availability_lock:
            return self._available

    def _mark_unavailable(self) -> None:
        with self._availability_lock:
            self._available = False
