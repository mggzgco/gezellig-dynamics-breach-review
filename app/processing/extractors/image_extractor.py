"""Image OCR extraction with layout-preserving TSV parsing."""

from __future__ import annotations

import io
import logging
import tempfile
from pathlib import Path

from PIL import Image, ImageOps

from app.processing.extractors.ocr_layout import extract_tsv_text
from app.processing.extractors.types import ExtractedText

logger = logging.getLogger(__name__)


def extract_with_metadata(data: bytes) -> ExtractedText:
    """Extract OCR text from an image while preserving line-level structure."""
    try:
        image = Image.open(io.BytesIO(data))
        normalized = ImageOps.exif_transpose(image)
    except Exception as exc:
        logger.error("Image extraction failed: %s", exc)
        return ExtractedText(
            extraction_method="image_ocr",
            parser="pillow+tesseract",
            ocr_used=True,
            ocr_page_count=1,
            low_confidence_ocr=True,
            warnings=[str(exc)[:200]],
        )

    with tempfile.TemporaryDirectory(prefix="pii-image-ocr-") as temp_dir:
        image_path = Path(temp_dir) / "image.png"
        normalized.save(image_path, format="PNG")
        extraction = extract_tsv_text(image_path)

    extraction.extraction_method = "image_ocr"
    extraction.parser = "pillow+tesseract"
    extraction.page_count = max(1, extraction.page_count or 1)
    extraction.structured = _looks_structured_ocr(extraction.text)
    return extraction


def extract(data: bytes) -> str:
    """Backward-compatible image extraction API."""
    return extract_with_metadata(data).text


def _looks_structured_ocr(text: str) -> bool:
    normalized = text.lower()
    return any(token in normalized for token in ("full name", "date of birth", "ssn", "member id", "mrn"))
