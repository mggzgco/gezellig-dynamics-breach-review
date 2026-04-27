import ast
import json
import re
from typing import Optional
from urllib import error, request


def request_json(base_url: str, timeout_seconds: float, path: str, payload: Optional[dict] = None, method: str = "POST") -> dict:
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request_object = request.Request(
        f"{base_url}{path}",
        data=body,
        headers=headers,
        method=method,
    )
    try:
        with request.urlopen(request_object, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(detail or str(exc)) from exc
    except error.URLError as exc:
        raise RuntimeError(str(exc.reason)) from exc


class StructuredObjectParser:
    @staticmethod
    def strip_code_fences(raw_text: str) -> str:
        stripped = raw_text.strip()
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```$", "", stripped)
        return stripped.strip()

    @staticmethod
    def clean_json_text(raw_text: str) -> str:
        cleaned = raw_text.strip()
        cleaned = cleaned.replace("“", '"').replace("”", '"').replace("’", "'")
        cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)
        cleaned = re.sub(r"\bTrue\b", "true", cleaned)
        cleaned = re.sub(r"\bFalse\b", "false", cleaned)
        cleaned = re.sub(r"\bNone\b", "null", cleaned)
        return cleaned

    @classmethod
    def parse_dict_like_text(cls, raw_text: Optional[str]) -> Optional[dict]:
        if not raw_text:
            return None
        candidate = raw_text.strip()
        if not candidate:
            return None

        for attempt in (candidate, cls.clean_json_text(candidate)):
            try:
                parsed = json.loads(attempt)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict):
                return parsed

        try:
            parsed = ast.literal_eval(candidate)
        except (SyntaxError, ValueError):
            return None
        return parsed if isinstance(parsed, dict) else None

    @classmethod
    def extract_first_json_object(cls, raw_text: str) -> Optional[str]:
        start = raw_text.find("{")
        if start < 0:
            return None

        depth = 0
        in_string = False
        escaped = False
        for index, char in enumerate(raw_text[start:], start=start):
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue

            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return raw_text[start:index + 1]
        return None

    @classmethod
    def extract_response_object(cls, raw_text: str) -> Optional[dict]:
        for candidate in (
            raw_text,
            cls.strip_code_fences(raw_text),
            cls.extract_first_json_object(raw_text),
        ):
            parsed = cls.parse_dict_like_text(candidate)
            if parsed:
                return parsed
        return None
