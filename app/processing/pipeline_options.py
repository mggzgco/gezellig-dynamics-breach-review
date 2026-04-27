"""Runtime options for the end-to-end analysis pipeline.

This keeps benchmark and UI entrypoints honest without relying on in-process
module monkeypatching. Production callers can use the defaults, while tests and
benchmark harnesses can opt into deterministic or forced-review modes
explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from app.processing.local_llm_attribution import LocalLLMAttributionHelper
from app.processing.local_llm_file_qa import LocalLLMFileQAHelper
from app.settings import LOCAL_LLM_FILE_QA_ENABLED, LOCAL_LLM_FILE_QA_WORKERS


FileQAHelperFactory = Callable[[], LocalLLMFileQAHelper]


@dataclass(slots=True)
class AnalysisPipelineOptions:
    """Explicit pipeline runtime knobs for UI, tests, and benchmark runs."""

    file_qa_enabled: bool = LOCAL_LLM_FILE_QA_ENABLED
    file_qa_workers: int = LOCAL_LLM_FILE_QA_WORKERS
    file_qa_helper_factory: Optional[FileQAHelperFactory] = None
    attribution_llm_helper: Optional[LocalLLMAttributionHelper] = None

    def build_file_qa_helper(self) -> LocalLLMFileQAHelper:
        """Create one file-QA helper instance using the configured factory."""
        if self.file_qa_helper_factory is not None:
            return self.file_qa_helper_factory()
        return LocalLLMFileQAHelper(enabled=self.file_qa_enabled)
