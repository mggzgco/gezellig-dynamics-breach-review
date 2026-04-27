"""Shared OCR image preprocessing helpers.

These helpers aim to improve OCR fidelity without inventing new content. They
normalize orientation, improve contrast, reduce noise, deskew slightly rotated
scans, and provide an adaptive-threshold variant for OCR engines that work
better on high-contrast text.
"""

from __future__ import annotations

from pathlib import Path
import tempfile

from PIL import Image, ImageFilter, ImageOps


def prepare_base_image_for_ocr(image: Image.Image) -> Image.Image:
    """Return a cleaned grayscale image suitable for OCR."""
    prepared = ImageOps.exif_transpose(image).convert("L")
    prepared = ImageOps.autocontrast(prepared)
    prepared = _upscale_for_ocr(prepared)
    prepared = prepared.filter(ImageFilter.MedianFilter(3))
    prepared = _deskew_image(prepared)
    return prepared.filter(ImageFilter.UnsharpMask(radius=1.6, percent=170, threshold=2))


def build_ocr_variants(image: Image.Image) -> dict[str, Image.Image]:
    """Return OCR image variants keyed by preprocessing strategy."""
    base = prepare_base_image_for_ocr(image)
    return {
        "base": base,
        "adaptive": adaptive_threshold(base),
    }


def save_ocr_variants(image_path: Path) -> tuple[tempfile.TemporaryDirectory, list[tuple[str, Path]]]:
    """Create temporary OCR-ready image variants from one image path."""
    image = Image.open(image_path)
    variants = build_ocr_variants(image)
    temp_dir = tempfile.TemporaryDirectory(prefix="pii-ocr-variants-")
    temp_path = Path(temp_dir.name)
    saved: list[tuple[str, Path]] = []
    for label, variant in variants.items():
        variant_path = temp_path / f"{label}.png"
        variant.save(variant_path, format="PNG")
        saved.append((label, variant_path))
    return temp_dir, saved


def adaptive_threshold(image: Image.Image, *, offset: int = 12) -> Image.Image:
    """Apply a simple local-threshold binarization around the local mean."""
    blurred = image.filter(ImageFilter.GaussianBlur(radius=7))
    source_pixels = image.load()
    blurred_pixels = blurred.load()
    width, height = image.size
    binary_pixels = [
        0 if source_pixels[x, y] < max(0, blurred_pixels[x, y] - offset) else 255
        for y in range(height)
        for x in range(width)
    ]
    binary = Image.new("L", image.size, 255)
    binary.putdata(binary_pixels)
    return binary.filter(ImageFilter.MedianFilter(3))


def _upscale_for_ocr(image: Image.Image) -> Image.Image:
    width, height = image.size
    min_dimension = min(width, height)
    if min_dimension >= 1400:
        return image
    scale = max(1.0, 1600 / max(1, min_dimension))
    return image.resize(
        (int(width * scale), int(height * scale)),
        resample=Image.Resampling.LANCZOS,
    )


def _deskew_image(image: Image.Image) -> Image.Image:
    """Rotate the image by the angle that maximizes horizontal text alignment."""
    coarse_angles = (-4, -2, 0, 2, 4)
    coarse_best = max(coarse_angles, key=lambda angle: _projection_score(_rotate_for_score(image, angle)))
    fine_angles = (coarse_best - 1.0, coarse_best - 0.5, coarse_best, coarse_best + 0.5, coarse_best + 1.0)
    best_angle = max(fine_angles, key=lambda angle: _projection_score(_rotate_for_score(image, angle)))
    if abs(best_angle) < 0.01:
        return image
    return image.rotate(best_angle, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=255)


def _rotate_for_score(image: Image.Image, angle: float) -> Image.Image:
    rotated = image.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=255)
    width, height = rotated.size
    if max(width, height) <= 600:
        return rotated
    scale = 600 / max(width, height)
    return rotated.resize((max(1, int(width * scale)), max(1, int(height * scale))), resample=Image.Resampling.BILINEAR)


def _projection_score(image: Image.Image) -> float:
    """Estimate horizontal line alignment via row darkness variance."""
    width, height = image.size
    pixels = image.load()
    row_step = max(1, height // 180)
    col_step = max(1, width // 240)
    row_scores: list[float] = []
    for y in range(0, height, row_step):
        darkness = 0.0
        for x in range(0, width, col_step):
            darkness += 255 - pixels[x, y]
        row_scores.append(darkness)
    if not row_scores:
        return 0.0
    mean = sum(row_scores) / len(row_scores)
    return sum((score - mean) ** 2 for score in row_scores) / len(row_scores)
