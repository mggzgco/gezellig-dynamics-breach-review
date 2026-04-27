import io
import logging
import os
from pathlib import Path
import tempfile

import striprtf.striprtf as striprtf

try:
    import magic
except ImportError:
    magic = None

from app.models import Attachment
from app.settings import MAX_ATTACHMENT_SIZE_MB, ZIP_MAX_RECURSION_DEPTH
from app.processing.extractors import (
    pdf_extractor,
    docx_extractor,
    xlsx_extractor,
    image_extractor,
    zip_extractor,
    plaintext_extractor,
)
from app.processing.extractors.types import ExtractedText

logger = logging.getLogger(__name__)


def extract_attachment_content(attachment: Attachment, depth: int = 0) -> ExtractedText:
    """Extract attachment text plus extraction metadata from one attachment payload."""
    if not attachment.data:
        return ExtractedText()

    size_warning = _validate_attachment_size(attachment)
    if size_warning:
        return size_warning

    mime_type = _resolve_mime_type(attachment)
    logger.debug(f"Extracting {attachment.filename} as MIME type: {mime_type}")

    try:
        return _extract_by_mime_type(attachment, mime_type, depth)
    except Exception as e:
        logger.error(f"Error extracting {attachment.filename}: {e}")
        return ExtractedText(warnings=[str(e)[:200]])


def extract_text_from_attachment(attachment: Attachment, depth: int = 0) -> str:
    """Backward-compatible attachment text extraction API."""
    return extract_attachment_content(attachment, depth=depth).text


def _validate_attachment_size(attachment: Attachment) -> ExtractedText | None:
    """Reject oversized attachments before MIME detection or parsing."""
    if len(attachment.data) <= MAX_ATTACHMENT_SIZE_MB * 1024 * 1024:
        return None
    logger.warning(f"Attachment {attachment.filename} exceeds max size, skipping")
    return ExtractedText(warnings=["attachment_exceeds_max_size"])


def _resolve_mime_type(attachment: Attachment) -> str:
    """Resolve the best MIME type using metadata, byte sniffing, and extension fallbacks."""
    ext = Path(attachment.filename).suffix.lower()
    ext_mime = _mime_from_extension(ext)
    mime_type = attachment.mime_type or ""

    if not mime_type and magic:
        try:
            mime_type = magic.from_buffer(attachment.data[:2048], mime=True)
        except Exception:
            mime_type = ""

    if (
        ext_mime != "application/octet-stream"
        and ext != ".zip"
        and mime_type in {"", "application/octet-stream", "binary/octet-stream", "application/zip", "application/x-zip-compressed"}
    ):
        return ext_mime
    if mime_type:
        return mime_type
    return ext_mime


def _extract_by_mime_type(attachment: Attachment, mime_type: str, depth: int) -> ExtractedText:
    """Dispatch one attachment to the appropriate concrete extractor."""
    if mime_type.startswith("application/pdf"):
        return pdf_extractor.extract_with_metadata(attachment.data)
    if mime_type in {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.ms-word.document.macroEnabled.12",
    }:
        return docx_extractor.extract_with_metadata(attachment.data)
    if mime_type == "application/msword":
        return _extract_legacy_word_document(attachment)
    if mime_type in {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel",
        "application/x-msexcel",
    }:
        return xlsx_extractor.extract_with_metadata(attachment.data)
    if mime_type in {"text/csv", "text/plain", "text/txt"}:
        return plaintext_extractor.extract_with_metadata(attachment.data)
    if mime_type.startswith("image/"):
        return image_extractor.extract_with_metadata(attachment.data)
    if mime_type in {"application/zip", "application/x-zip-compressed"}:
        return _extract_zip_archive(attachment, depth)
    if mime_type == "application/x-rar-compressed":
        logger.info(f"RAR files not supported: {attachment.filename}")
        return ExtractedText(warnings=["rar_not_supported"])
    if mime_type == "message/rfc822":
        return _extract_nested_email(attachment, depth)
    if mime_type in {"application/vnd.ms-outlook", "application/x-msg"}:
        return _extract_outlook_msg(attachment, depth)
    if mime_type == "text/rtf" or Path(attachment.filename).suffix.lower() == ".rtf":
        return _extract_rtf_document(attachment)

    logger.debug(f"No handler for MIME type {mime_type}, treating as plaintext")
    return plaintext_extractor.extract_with_metadata(attachment.data)


def _extract_legacy_word_document(attachment: Attachment) -> ExtractedText:
    """Attempt DOC parsing through the DOCX extractor shim before giving up."""
    try:
        return docx_extractor.extract_with_metadata(attachment.data)
    except Exception:
        logger.debug("DOCX extractor failed for DOC file, skipping")
        return ExtractedText(warnings=["doc_parse_failed"])


def _extract_zip_archive(attachment: Attachment, depth: int) -> ExtractedText:
    """Extract flattened text from ZIP archives with bounded recursion."""
    text = zip_extractor.extract(attachment.data, depth=depth, max_depth=ZIP_MAX_RECURSION_DEPTH)
    return ExtractedText(text=text, extraction_method="zip_archive", parser="zipfile", structured=True)


def _extract_nested_email(attachment: Attachment, depth: int) -> ExtractedText:
    """Parse a nested EML and recursively extract any embedded attachments."""
    from app.processing.eml_parser import parse_eml_file

    temp_path = None
    with tempfile.NamedTemporaryFile(suffix=".eml", delete=False) as tmp:
        tmp.write(attachment.data)
        tmp.flush()
        temp_path = tmp.name
    try:
        nested_result = parse_eml_file(temp_path)
    except Exception as exc:
        logger.warning(f"Failed to parse nested EML: {exc}")
        return ExtractedText(warnings=[str(exc)[:200]])
    finally:
        if temp_path:
            try:
                os.unlink(temp_path)
            except FileNotFoundError:
                pass
            except OSError as exc:
                logger.warning("Could not delete nested EML temp file %s: %s", temp_path, exc)

    inner_texts = []
    inner_warnings: list[str] = []
    for nested_attachment in nested_result.get("attachments", []):
        nested_extraction = extract_attachment_content(nested_attachment, depth=depth + 1)
        if nested_extraction.text:
            inner_texts.append(nested_extraction.text)
        inner_warnings.extend(nested_extraction.warnings)

    return ExtractedText(
        text=(nested_result.get("body_text", "") + "\n".join(inner_texts)).strip(),
        extraction_method="nested_email",
        parser="email.parser",
        structured=bool(inner_texts),
        warnings=inner_warnings,
    )


def _extract_outlook_msg(attachment: Attachment, depth: int) -> ExtractedText:
    """Extract text and recursive attachments from an Outlook MSG file."""
    try:
        import extract_msg

        with extract_msg.openMsg(io.BytesIO(attachment.data)) as msg:
            text_parts = [msg.body or ""]
            warnings: list[str] = []
            for subatt in msg.attachments:
                extracted = extract_attachment_content(
                    Attachment(
                        filename=subatt.filename,
                        mime_type="application/octet-stream",
                        data=subatt.open().read(),
                        source_eml="",
                    ),
                    depth=depth + 1,
                )
                if extracted.text:
                    text_parts.append(extracted.text)
                warnings.extend(extracted.warnings)
            return ExtractedText(
                text="\n".join(text_parts),
                extraction_method="outlook_msg",
                parser="extract_msg",
                structured=bool(msg.attachments),
                warnings=warnings,
            )
    except Exception as exc:
        logger.warning(f"MSG extraction failed: {exc}")
        return ExtractedText(warnings=[str(exc)[:200]])


def _extract_rtf_document(attachment: Attachment) -> ExtractedText:
    """Extract plain text from RTF content."""
    try:
        text = striprtf.rtf_to_text(attachment.data.decode("utf-8", errors="ignore"))
        return ExtractedText(text=text, extraction_method="rtf_text", parser="striprtf")
    except Exception as exc:
        logger.warning(f"RTF extraction failed: {exc}")
        return ExtractedText(warnings=[str(exc)[:200]])


def _mime_from_extension(ext: str) -> str:
    """Map file extension to MIME type."""
    ext_map = {
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".doc": "application/msword",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xls": "application/vnd.ms-excel",
        ".csv": "text/csv",
        ".txt": "text/plain",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".tiff": "image/tiff",
        ".zip": "application/zip",
        ".msg": "application/vnd.ms-outlook",
        ".eml": "message/rfc822",
        ".rtf": "text/rtf",
    }
    return ext_map.get(ext, "application/octet-stream")
