import chardet
import csv
import io

from app.processing.extractors.table_renderer import render_rows
from app.processing.extractors.types import ExtractedText


def _decode(data: bytes) -> str:
    try:
        return data.decode("utf-8", errors="ignore")
    except Exception:
        pass

    try:
        detected = chardet.detect(data)
        encoding = detected.get("encoding", "utf-8")
        if encoding:
            return data.decode(encoding, errors="ignore")
    except Exception:
        pass

    return data.decode("latin-1", errors="ignore")


def _looks_structured(text: str) -> bool:
    return _parse_structured_rows(text) is not None


def _parse_structured_rows(text: str) -> list[list[str]] | None:
    for delimiter in (",", "\t", "|"):
        try:
            reader = csv.reader(io.StringIO(text), delimiter=delimiter)
            rows = [row for row in reader if any(cell.strip() for cell in row)]
        except Exception:
            continue

        if len(rows) < 2:
            continue

        header_len = len(rows[0])
        if header_len < 2:
            continue
        if all(len(row) == header_len for row in rows[1:]):
            return rows
    return None


def _render_structured_text(text: str) -> str:
    rows = _parse_structured_rows(text)
    if rows:
        return "\n".join(render_rows("Text", rows))
    return text


def extract_with_metadata(data: bytes) -> ExtractedText:
    """Extract plain text and flag simple structured/table-like layouts."""
    text = _decode(data)
    if _looks_structured(text):
        return ExtractedText(
            text=_render_structured_text(text),
            extraction_method="structured_text",
            parser="csv_reader",
            table_count=1,
            structured=True,
        )
    return ExtractedText(text=text, extraction_method="plain_text", parser="charset_decode")


def extract(data: bytes) -> str:
    """Backward-compatible plain-text extraction API."""
    return extract_with_metadata(data).text
