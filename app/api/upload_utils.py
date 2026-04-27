"""Helpers for safe, bounded upload persistence."""

from __future__ import annotations

from pathlib import Path
import re

from fastapi import HTTPException, UploadFile


UPLOAD_CHUNK_SIZE_BYTES = 1024 * 1024
SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def sanitize_upload_filename(raw_filename: str) -> str:
    """Normalize one client-supplied upload filename into a safe `.eml` basename."""
    filename = Path(raw_filename or "").name.strip().replace("\x00", "")
    if not filename:
        raise HTTPException(status_code=400, detail="One or more uploaded files had no filename.")

    filename = SAFE_FILENAME_RE.sub("_", filename).lstrip(".")
    if not filename or not filename.lower().endswith(".eml"):
        raise HTTPException(status_code=400, detail="Only `.eml` files can be uploaded.")
    return filename


def unique_upload_path(uploads_dir: Path, filename: str) -> Path:
    """Generate a collision-free path inside the job upload directory."""
    candidate = uploads_dir / filename
    stem = candidate.stem
    suffix = candidate.suffix
    counter = 2
    while candidate.exists():
        candidate = uploads_dir / f"{stem}_{counter}{suffix}"
        counter += 1

    uploads_root = uploads_dir.resolve()
    candidate_resolved = candidate.resolve()
    if uploads_root not in candidate_resolved.parents:
        raise HTTPException(status_code=400, detail="Unsafe upload filename was rejected.")
    return candidate


async def save_upload_file(
    upload: UploadFile,
    uploads_dir: Path,
    *,
    max_bytes: int,
    sanitized_filename: str | None = None,
) -> Path:
    """Persist one upload incrementally with filename sanitization and size checks."""
    filename = sanitized_filename or sanitize_upload_filename(upload.filename or "")
    file_path = unique_upload_path(uploads_dir, filename)
    bytes_written = 0

    try:
        with file_path.open("wb") as handle:
            while True:
                chunk = await upload.read(UPLOAD_CHUNK_SIZE_BYTES)
                if not chunk:
                    break
                bytes_written += len(chunk)
                if bytes_written > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Uploaded file '{filename}' exceeded the {max_bytes // (1024 * 1024)} MB limit.",
                    )
                handle.write(chunk)
    except Exception:
        if file_path.exists():
            file_path.unlink()
        raise
    finally:
        await upload.close()

    return file_path
