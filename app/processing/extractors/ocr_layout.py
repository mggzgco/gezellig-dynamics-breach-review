"""Layout-preserving OCR helpers built around the local Tesseract binary."""

from __future__ import annotations

import csv
import logging
import re
import subprocess
from collections import defaultdict
from pathlib import Path

from app.processing.extractors.ocr_normalization import normalize_ocr_lines
from app.processing.extractors.ocr_preprocessing import save_ocr_variants
from app.processing.extractors.types import ExtractedText
from app.settings import OCR_LANGUAGES, OCR_LOW_CONFIDENCE_THRESHOLD, OCR_MIN_WORDS

logger = logging.getLogger(__name__)


def extract_tsv_text(image_path: Path, *, prefix: str | None = None) -> ExtractedText:
    """Run bounded multi-pass Tesseract OCR and choose the strongest result."""
    temp_dir, variants = save_ocr_variants(image_path)
    try:
        first_passes = {
            variant_label: _tag_selected_pass(_run_tesseract_tsv(variant_path, prefix=prefix, page_segmentation_mode=6), variant_label, 6)
            for variant_label, variant_path in variants
        }
        best_variant_label, best = max(first_passes.items(), key=lambda item: _ocr_quality_score(item[1]))
        if not _should_retry_with_additional_modes(best):
            return best

        best_variant_path = next(path for label, path in variants if label == best_variant_label)
        candidates = [best]
        for page_segmentation_mode in (4, 11):
            candidate = _run_tesseract_tsv(best_variant_path, prefix=prefix, page_segmentation_mode=page_segmentation_mode)
            candidates.append(_tag_selected_pass(candidate, best_variant_label, page_segmentation_mode))
        return max(candidates, key=_ocr_quality_score)
    finally:
        temp_dir.cleanup()


def _run_tesseract_tsv(
    image_path: Path,
    *,
    prefix: str | None,
    page_segmentation_mode: int,
) -> ExtractedText:
    """Run one Tesseract TSV pass with the requested page segmentation mode."""
    command = [
        "tesseract",
        str(image_path),
        "stdout",
        "-l",
        OCR_LANGUAGES,
        "--oem",
        "1",
        "--psm",
        str(page_segmentation_mode),
        "-c",
        "preserve_interword_spaces=1",
        "tsv",
    ]
    try:
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
    except FileNotFoundError:
        return ExtractedText(
            extraction_method="ocr_tsv",
            parser="tesseract",
            ocr_used=True,
            ocr_page_count=1,
            low_confidence_ocr=True,
            warnings=["tesseract_not_installed"],
        )
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        logger.warning("Tesseract OCR failed for %s: %s", image_path, stderr or exc)
        return ExtractedText(
            extraction_method="ocr_tsv",
            parser="tesseract",
            ocr_used=True,
            ocr_page_count=1,
            low_confidence_ocr=True,
            warnings=[stderr[:200] or "tesseract_failed"],
        )

    return _parse_tsv_output(completed.stdout, prefix=prefix)


def _parse_tsv_output(raw_tsv: str, *, prefix: str | None = None) -> ExtractedText:
    """Convert Tesseract TSV into line-preserving text and OCR confidence stats."""
    if not raw_tsv.strip():
        return ExtractedText(
            extraction_method="ocr_tsv",
            parser="tesseract",
            ocr_used=True,
            ocr_page_count=1,
            low_confidence_ocr=True,
            warnings=["empty_ocr_output"],
        )

    line_words: dict[tuple[int, int, int, int], list[tuple[int, str]]] = defaultdict(list)
    confidences: list[float] = []
    page_numbers: set[int] = set()

    reader = csv.DictReader(raw_tsv.splitlines(), delimiter="\t")
    for row in reader:
        if not row:
            continue
        text = (row.get("text") or "").strip()
        if not text:
            continue
        try:
            level = int(row.get("level") or 0)
            page_num = int(row.get("page_num") or 0)
            block_num = int(row.get("block_num") or 0)
            par_num = int(row.get("par_num") or 0)
            line_num = int(row.get("line_num") or 0)
            left = int(float(row.get("left") or 0))
            conf = float(row.get("conf") or -1)
        except ValueError:
            continue
        if level != 5:
            continue
        page_numbers.add(page_num)
        if conf >= 0:
            confidences.append(conf)
        line_words[(page_num, block_num, par_num, line_num)].append((left, text))

    rendered_lines: list[str] = []
    for line_key in sorted(line_words):
        words = [word for _, word in sorted(line_words[line_key], key=lambda item: item[0])]
        if not words:
            continue
        rendered_lines.append(" ".join(words))

    rendered_lines, normalization_warnings = normalize_ocr_lines(rendered_lines)
    if prefix and rendered_lines:
        rendered_text = f"{prefix}\n" + "\n".join(rendered_lines)
    else:
        rendered_text = "\n".join(rendered_lines)

    avg_confidence = round(sum(confidences) / len(confidences), 2) if confidences else 0.0
    low_confidence = avg_confidence < OCR_LOW_CONFIDENCE_THRESHOLD or len(confidences) < OCR_MIN_WORDS
    warnings: list[str] = []
    if not rendered_text.strip():
        warnings.append("empty_ocr_output")
    if low_confidence:
        warnings.append("low_confidence_ocr")
    warnings.extend(normalization_warnings)

    page_count = max(page_numbers) if page_numbers else 1
    return ExtractedText(
        text=rendered_text,
        extraction_method="ocr_tsv",
        parser="tesseract",
        page_count=page_count,
        ocr_used=True,
        ocr_page_count=page_count,
        ocr_avg_confidence=avg_confidence,
        low_confidence_ocr=low_confidence,
        warnings=_dedupe_preserve_order(warnings),
    )


def _should_retry_with_additional_modes(extraction: ExtractedText) -> bool:
    """Retry OCR with alternate layout modes when the best primary pass is still weak."""
    if not extraction.text.strip():
        return True
    if extraction.low_confidence_ocr:
        return True
    if len(extraction.text.split()) < OCR_MIN_WORDS:
        return True
    return _structured_field_score(extraction.text) < 2


def _ocr_quality_score(extraction: ExtractedText) -> float:
    """Score OCR passes by confidence, coverage, and recovered field structure."""
    text_lower = extraction.text.lower()
    field_hits = sum(
        token in text_lower
        for token in (
            "full name",
            "date of birth",
            "dob",
            "ssn",
            "mrn",
            "medicare",
            "address",
            "phone",
            "email",
        )
    )
    field_value_bonus = _structured_field_score(extraction.text) * 16.0
    word_count = len(extraction.text.split())
    penalty = 18.0 if extraction.low_confidence_ocr else 0.0
    return extraction.ocr_avg_confidence + (word_count * 0.4) + (field_hits * 10.0) + field_value_bonus - penalty


def _structured_field_score(text: str) -> int:
    """Score recovered OCR text based on labeled field/value quality."""
    score = 0
    for line in text.splitlines():
        line_lower = line.lower()
        if "full name:" in line_lower and len(line.split(":", 1)[-1].strip().split()) >= 2:
            score += 1
        if ("date of birth:" in line_lower or line_lower.startswith("dob:")) and _line_has_date(line):
            score += 1
        if line_lower.startswith("ssn:") and _line_has_ssn(line):
            score += 1
        if "address:" in line_lower and _line_looks_like_address(line):
            score += 1
    return score


def _line_has_date(line: str) -> bool:
    return bool(_DATE_VALUE_RE.search(line))


def _line_has_ssn(line: str) -> bool:
    return bool(_SSN_VALUE_RE.search(line))


def _line_looks_like_address(line: str) -> bool:
    return bool(_ADDRESS_VALUE_RE.search(line))


def _tag_selected_pass(extraction: ExtractedText, variant_label: str, page_segmentation_mode: int) -> ExtractedText:
    warnings = list(extraction.warnings)
    warnings.append(f"ocr_variant_{variant_label}")
    warnings.append(f"ocr_psm_{page_segmentation_mode}")
    extraction.warnings = _dedupe_preserve_order(warnings)
    return extraction


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


_DATE_VALUE_RE = re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b")
_SSN_VALUE_RE = re.compile(r"\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b")
_ADDRESS_VALUE_RE = re.compile(
    r"\b\d{1,6}\s+[A-Za-z0-9 .'-]+,\s*[A-Za-z .'-]+,\s*[A-Z]{2}\s+\d{5}(?:-\d{4})?\b"
)
