"""PDF extraction with digital-text, table, and OCR fallback phases."""

from __future__ import annotations

import io
import logging
import subprocess
import tempfile
from pathlib import Path

import pdfplumber

from app.processing.extractors.ocr_layout import extract_tsv_text
from app.processing.extractors.table_renderer import render_rows
from app.processing.extractors.types import ExtractedText
from app.settings import PDF_PAGE_OCR_TEXT_THRESHOLD

logger = logging.getLogger(__name__)


def extract_with_metadata(data: bytes) -> ExtractedText:
    """Extract PDF content while preserving page and table structure where possible."""
    parts: list[str] = []
    warnings: list[str] = []
    table_count = 0
    page_count = 0
    ocr_confidences: list[float] = []
    ocr_page_count = 0

    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            page_count = len(pdf.pages)
            for page_number, page in enumerate(pdf.pages, start=1):
                page_text = (page.extract_text(layout=True) or "").strip()
                page_parts: list[str] = []
                if page_text:
                    page_parts.append(f"[PDF Page {page_number}]\n{page_text}")

                page_tables = page.extract_tables() or []
                for table_index, table in enumerate(page_tables, start=1):
                    cleaned_rows = _clean_table_rows(table)
                    if not cleaned_rows:
                        continue
                    table_count += 1
                    page_parts.extend(render_rows(f"PDF Page {page_number} Table {table_index}", cleaned_rows))

                if len(page_text) < PDF_PAGE_OCR_TEXT_THRESHOLD:
                    ocr_result = _ocr_pdf_page(data, page_number)
                    if ocr_result.text.strip():
                        ocr_page_count += 1
                        if ocr_result.ocr_avg_confidence:
                            ocr_confidences.append(ocr_result.ocr_avg_confidence)
                        page_parts.append(f"[PDF Page {page_number} OCR]\n{ocr_result.text}")
                    warnings.extend(ocr_result.warnings)

                if page_parts:
                    parts.append("\n".join(page_parts))
    except Exception as exc:
        logger.warning("PDF extraction failed: %s", exc)
        warnings.append(str(exc)[:200])

    avg_ocr_confidence = round(sum(ocr_confidences) / len(ocr_confidences), 2) if ocr_confidences else 0.0
    low_confidence_ocr = any("low_confidence_ocr" in warning for warning in warnings)
    if not parts and not warnings:
        warnings.append("empty_pdf_extraction")

    return ExtractedText(
        text="\n\n".join(part for part in parts if part.strip()),
        extraction_method="pdf_layout_and_ocr",
        parser="pdfplumber+pdftoppm+tesseract",
        page_count=page_count,
        table_count=table_count,
        structured=table_count > 0,
        ocr_used=ocr_page_count > 0,
        ocr_page_count=ocr_page_count,
        ocr_avg_confidence=avg_ocr_confidence,
        low_confidence_ocr=low_confidence_ocr,
        warnings=_dedupe_preserve_order(warnings),
    )


def extract(data: bytes) -> str:
    """Backward-compatible PDF extraction API."""
    return extract_with_metadata(data).text


def _ocr_pdf_page(pdf_bytes: bytes, page_number: int) -> ExtractedText:
    """Render one PDF page to PNG and OCR it with Tesseract TSV output."""
    with tempfile.TemporaryDirectory(prefix="pii-pdf-ocr-") as temp_dir:
        pdf_path = Path(temp_dir) / "input.pdf"
        image_prefix = Path(temp_dir) / "page"
        pdf_path.write_bytes(pdf_bytes)
        command = [
            "pdftoppm",
            "-r",
            "220",
            "-f",
            str(page_number),
            "-l",
            str(page_number),
            "-png",
            str(pdf_path),
            str(image_prefix),
        ]
        try:
            subprocess.run(command, check=True, capture_output=True, text=True, encoding="utf-8", errors="ignore")
        except FileNotFoundError:
            return ExtractedText(
                extraction_method="pdf_page_ocr",
                parser="pdftoppm+tesseract",
                ocr_used=True,
                ocr_page_count=1,
                low_confidence_ocr=True,
                warnings=["pdftoppm_not_installed"],
            )
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip()
            logger.warning("pdftoppm failed for PDF page %s: %s", page_number, stderr or exc)
            return ExtractedText(
                extraction_method="pdf_page_ocr",
                parser="pdftoppm+tesseract",
                ocr_used=True,
                ocr_page_count=1,
                low_confidence_ocr=True,
                warnings=[stderr[:200] or "pdftoppm_failed"],
            )

        image_candidates = sorted(Path(temp_dir).glob("page-*.png"))
        if not image_candidates:
            return ExtractedText(
                extraction_method="pdf_page_ocr",
                parser="pdftoppm+tesseract",
                ocr_used=True,
                ocr_page_count=1,
                low_confidence_ocr=True,
                warnings=["pdftoppm_no_images"],
            )

        extraction = extract_tsv_text(image_candidates[0], prefix=f"[Rendered Page {page_number}]")
        extraction.extraction_method = "pdf_page_ocr"
        extraction.parser = "pdftoppm+tesseract"
        return extraction


def _clean_table_rows(raw_rows) -> list[list[str]]:
    cleaned_rows: list[list[str]] = []
    for row in raw_rows or []:
        cleaned_row = [str(cell).strip() if cell is not None else "" for cell in row]
        if any(cell for cell in cleaned_row):
            cleaned_rows.append(cleaned_row)
    return cleaned_rows


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered
