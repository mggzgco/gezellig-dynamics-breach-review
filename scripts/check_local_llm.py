#!/usr/bin/env python3
"""
Lightweight diagnostic for the optional local LLM attribution runtime.
"""
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.processing.local_llm_attribution import LocalLLMAttributionHelper
from app.processing.local_llm_common import request_json, StructuredObjectParser


def main() -> int:
    helper = LocalLLMAttributionHelper()
    ok, message = helper.probe()
    generation_status = "not_checked"
    generation_message = ""

    if ok:
        try:
            response = request_json(
                helper.base_url,
                min(helper.timeout_seconds, 15.0),
                "/api/generate",
                payload={
                    "model": helper.model,
                    "prompt": 'Return only {"ok": true}.',
                    "stream": False,
                    "think": False,
                    "format": {
                        "type": "object",
                        "properties": {"ok": {"type": "boolean"}},
                        "required": ["ok"],
                    },
                    "options": {
                        "temperature": 0,
                        "num_predict": 32,
                    },
                },
                method="POST",
            )
            parsed = StructuredObjectParser.extract_response_object(str(response.get("response", "")))
            if isinstance(parsed, dict) and parsed.get("ok") is True:
                generation_status = "ready"
                generation_message = "Structured generation probe succeeded."
            else:
                generation_status = "degraded"
                generation_message = "Model responded, but structured generation probe did not validate."
                ok = False
        except Exception as exc:
            generation_status = "degraded"
            generation_message = f"Structured generation probe failed: {exc}"
            ok = False

    print("Local LLM attribution runtime")
    print(json.dumps(
        {
            "enabled": helper.enabled,
            "provider": helper.provider,
            "model": helper.model,
            "base_url": helper.base_url,
            "status": "ready" if ok else "not_ready",
            "message": message,
            "generation_status": generation_status,
            "generation_message": generation_message,
        },
        indent=2,
    ))

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
