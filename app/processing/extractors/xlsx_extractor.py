import io
import openpyxl
import xlrd
import logging

from app.processing.extractors.table_renderer import render_rows
from app.processing.extractors.types import ExtractedText

logger = logging.getLogger(__name__)


def extract_with_metadata(data: bytes) -> ExtractedText:
    """Extract workbook sheets as labeled table rows."""
    # Try XLSX first (modern format)
    try:
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        rows = []
        sheet_count = 0
        for ws in wb.worksheets:
            sheet_count += 1
            sheet_rows = [[str(cell) if cell is not None else "" for cell in row] for row in ws.iter_rows(values_only=True)]
            rows.extend(render_rows(ws.title, sheet_rows))
        return ExtractedText(
            text="\n".join(rows),
            extraction_method="spreadsheet_rows",
            parser="openpyxl",
            table_count=sheet_count,
            structured=sheet_count > 0,
        )
    except Exception as e:
        logger.debug(f"XLSX extraction failed, trying XLS: {e}")

    # Fallback to XLS (legacy format)
    try:
        wb = xlrd.open_workbook(file_contents=data)
        rows = []
        sheet_count = 0
        for ws in wb.sheets():
            sheet_count += 1
            sheet_rows = []
            for row_idx in range(ws.nrows):
                sheet_rows.append([str(ws.cell_value(row_idx, col_idx)) for col_idx in range(ws.ncols)])
            rows.extend(render_rows(ws.name, sheet_rows))
        return ExtractedText(
            text="\n".join(rows),
            extraction_method="spreadsheet_rows",
            parser="xlrd",
            table_count=sheet_count,
            structured=sheet_count > 0,
        )
    except Exception as e:
        logger.error(f"XLS extraction failed: {e}")
        return ExtractedText(
            extraction_method="spreadsheet_rows",
            parser="openpyxl/xlrd",
            warnings=[str(e)[:200]],
        )


def extract(data: bytes) -> str:
    """Backward-compatible spreadsheet extraction API."""
    return extract_with_metadata(data).text
