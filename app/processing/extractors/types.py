"""Shared extractor result types.

Keeping extractor outputs structured lets the pipeline expose extraction
quality, OCR usage, and table/layout signals without forcing every caller to
understand extractor-specific details.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ExtractedText:
    """Text plus extraction-quality metadata for one document source."""

    text: str = ""
    extraction_method: str = "plain_text"
    parser: str = ""
    page_count: int = 0
    table_count: int = 0
    structured: bool = False
    ocr_used: bool = False
    ocr_page_count: int = 0
    ocr_avg_confidence: float = 0.0
    low_confidence_ocr: bool = False
    warnings: list[str] = field(default_factory=list)

