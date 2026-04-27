"""Prompt assembly helpers for file-level AI QA."""

from __future__ import annotations

import json
import re

from app.models import EmailAnalysisResult
from app.processing.local_llm_file_qa_policy import source_priority


def build_file_qa_prompt(result: EmailAnalysisResult, *, known_pii_types: set[str], max_context_chars: int) -> str:
    """Build a bounded QA prompt around deterministic findings and nearby context."""
    findings = [
        {
            "type": match.pii_type,
            "risk": match.risk_level,
            "source_ref": match.source_ref,
            "excerpt": match.excerpt,
            "confidence": match.confidence,
        }
        for match in sorted(result.pii_matches, key=lambda item: (-item.confidence, item.source_ref))[:8]
    ]

    payload = {
        "eml_filename": result.eml_filename,
        "subject": result.subject,
        "from_address": result.from_address,
        "to_addresses": result.to_addresses[:4],
        "attachments": [
            {
                "filename": _attachment_value(item, "filename"),
                "mime_type": _attachment_value(item, "mime_type"),
                "structured": _attachment_value(item, "structured", False),
                "ocr_used": _attachment_value(item, "ocr_used", False),
                "low_confidence_ocr": _attachment_value(item, "low_confidence_ocr", False),
            }
            for item in result.attachments_processed[:5]
        ],
        "source_extractions": [
            {
                "source_ref": source_ref,
                "method": metadata.extraction_method,
                "table_count": metadata.table_count,
                "structured": metadata.structured,
                "ocr_used": metadata.ocr_used,
                "ocr_avg_confidence": metadata.ocr_avg_confidence,
                "low_confidence_ocr": metadata.low_confidence_ocr,
            }
            for source_ref, metadata in sorted(result.source_extractions.items(), key=lambda item: source_priority(item[0]))
            if metadata.structured or metadata.ocr_used or metadata.table_count or metadata.warnings
        ][:5],
        "deterministic_findings": findings,
        "source_context": "\n\n".join(build_context_parts(result, max_context_chars=max_context_chars))[:max_context_chars],
    }
    instructions = (
        "You are performing quality assurance on a deterministic PII breach scan. "
        "Do not restate every finding. Decide whether the file needs human review because the scan likely missed material PII, "
        "or because some detected findings look questionable. Be conservative: if uncertain, require human review. "
        "Only use these PII types when naming suspected types: "
        f"{', '.join(sorted(known_pii_types))}. "
        "Keep the reason short and concrete. "
        "Evidence quotes must be exact substrings from the provided context. "
        "Return only one JSON object."
    )
    return f"{instructions}\n\nContext JSON:\n{json.dumps(payload, ensure_ascii=True, indent=2)}"


def build_context_parts(result: EmailAnalysisResult, *, max_context_chars: int) -> list[str]:
    """Prefer finding-local context, then fill remaining budget with source fallbacks."""
    context_parts: list[str] = []
    used_refs: set[str] = set()

    if result.pii_matches:
        for match in sorted(result.pii_matches, key=lambda item: (-item.confidence, item.source_ref))[:12]:
            source_text = result.source_texts.get(match.source_ref, "")
            if not source_text.strip():
                continue
            snippet = extract_snippet(source_text, match.char_offset, max_context_chars=max_context_chars)
            part = f"[{match.source_ref}]\n{snippet}"
            if part in context_parts:
                continue
            remaining = max_context_chars - sum(len(existing) for existing in context_parts)
            if remaining <= 120:
                break
            context_parts.append(part[:remaining])
            used_refs.add(match.source_ref)

    fallback_limit = 160 if result.pii_matches else 140
    remaining_refs = list(result.source_texts.items())
    if not result.pii_matches:
        remaining_refs.sort(key=lambda item: (source_priority(item[0]), item[0]))
    else:
        remaining_refs.sort(key=lambda item: item[0])

    for source_ref, text in remaining_refs:
        if source_ref in used_refs or not text.strip():
            continue
        remaining = max_context_chars - sum(len(existing) for existing in context_parts)
        if remaining <= 120:
            break
        snippet = trim_text(text, limit=min(fallback_limit, remaining))
        context_parts.append(f"[{source_ref}]\n{snippet}")

    return context_parts


def extract_snippet(text: str, char_offset: int, *, max_context_chars: int, radius: int = 180) -> str:
    """Pull a bounded snippet around one deterministic finding offset."""
    if not text.strip():
        return ""
    start = max(0, char_offset - radius)
    end = min(len(text), char_offset + radius)
    snippet = text[start:end].strip()
    return trim_text(snippet, limit=min(len(snippet), min(420, max_context_chars)))


def trim_text(text: str, *, limit: int) -> str:
    """Trim text to a prompt-safe size."""
    return text.strip()[:limit]


def normalize_text(value: str) -> str:
    """Whitespace-normalize text for robust substring checks."""
    return re.sub(r"\s+", " ", value).strip().lower()


def _attachment_value(attachment, field: str, default=""):
    """Read transitional attachment records that may still be dict-shaped in tests."""
    if hasattr(attachment, field):
        return getattr(attachment, field)
    if isinstance(attachment, dict):
        return attachment.get(field, default)
    return default
