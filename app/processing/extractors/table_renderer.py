import re

_GENERIC_KEY_HEADERS = {"field", "label", "attribute", "item", "key", "name"}
_GENERIC_VALUE_HEADERS = {"value", "data", "detail", "entry", "content"}


def _humanize_header(value: str) -> str:
    return str(value).strip().replace("_", " ")


def _is_generic_key_value_sheet(headers: list[str]) -> bool:
    if len(headers) < 2:
        return False
    first = headers[0].strip().lower()
    second = headers[1].strip().lower()
    return first in _GENERIC_KEY_HEADERS and second in _GENERIC_VALUE_HEADERS


def _looks_like_header_row(headers: list[str]) -> bool:
    non_empty = [header.strip() for header in headers if header and header.strip()]
    if len(non_empty) < 2:
        return False
    unique = {header.lower() for header in non_empty}
    if len(unique) != len(non_empty):
        return False

    alpha_like = 0
    value_like = 0
    for header in non_empty:
        if re.search(r"[A-Za-z]", header):
            alpha_like += 1
        if re.search(r"\d", header):
            value_like += 1

    return alpha_like == len(non_empty) and value_like <= max(1, len(non_empty) // 3)


def _render_generic_key_value_rows(headers: list[str], rows: list[list[str]]) -> list[str]:
    rendered: list[str] = []
    for row in rows:
        label = str(row[0]).strip() if len(row) > 0 else ""
        value = str(row[1]).strip() if len(row) > 1 else ""
        if not label and not value:
            continue

        extras = []
        for index in range(2, len(row)):
            extra_value = str(row[index]).strip()
            if not extra_value:
                continue
            header = headers[index] if index < len(headers) else ""
            if header:
                extras.append(f"{header}: {extra_value}")
            else:
                extras.append(extra_value)

        rendered_line = f"{_humanize_header(label)}: {value}" if value else _humanize_header(label)
        if extras:
            rendered_line = f"{rendered_line}\t" + "\t".join(extras)
        rendered.append(rendered_line)
    return rendered


def render_rows(title: str, raw_rows: list[list[str]]) -> list[str]:
    rendered = [f"[Sheet: {title}]"]
    non_empty_rows = [[str(cell).strip() for cell in row] for row in raw_rows if any(str(cell).strip() for cell in row)]
    if not non_empty_rows:
        return rendered

    headers = [_humanize_header(cell) for cell in non_empty_rows[0]]
    if _looks_like_header_row(headers):
        if _is_generic_key_value_sheet(headers):
            rendered.extend(_render_generic_key_value_rows(headers, non_empty_rows[1:]))
            return rendered

        rendered.append("\t".join(headers))
        for row in non_empty_rows[1:]:
            pairs = []
            for index, cell in enumerate(row):
                value = str(cell).strip()
                if not value:
                    continue
                header = headers[index] if index < len(headers) else ""
                if header:
                    pairs.append(f"{header}: {value}")
                else:
                    pairs.append(value)
            if pairs:
                rendered.append("\t".join(pairs))
        return rendered

    for row in non_empty_rows:
        row_str = "\t".join(cell for cell in row if cell)
        if row_str:
            rendered.append(row_str)
    return rendered
