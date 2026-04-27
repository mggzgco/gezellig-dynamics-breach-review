import io
import zipfile
import logging

logger = logging.getLogger(__name__)


def extract(data: bytes, depth: int = 0, max_depth: int = 3, max_size_mb: int = 50) -> str:
    """Extract text from ZIP archives recursively"""
    if depth > max_depth:
        logger.warning(f"ZIP max recursion depth ({max_depth}) reached")
        return ""

    texts = []
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for info in zf.infolist():
                # Skip if file is too large
                if info.file_size > max_size_mb * 1024 * 1024:
                    logger.warning(f"Skipping oversized file in ZIP: {info.filename}")
                    continue

                try:
                    inner_bytes = zf.read(info.filename)
                    # Import here to avoid circular dependency
                    from app.processing.attachment_handler import extract_text_from_attachment
                    from app.models import Attachment
                    attachment = Attachment(
                        filename=info.filename,
                        mime_type="application/octet-stream",
                        data=inner_bytes,
                        source_eml=""
                    )
                    # Recursive extraction
                    extracted = extract_text_from_attachment(attachment, depth=depth + 1)
                    if extracted:
                        texts.append(f"[ZIP member: {info.filename}]\n{extracted}")
                except Exception as e:
                    logger.debug(f"Failed to extract {info.filename} from ZIP: {e}")
        return "\n".join(texts)
    except Exception as e:
        logger.error(f"ZIP extraction failed: {e}")
        return ""
