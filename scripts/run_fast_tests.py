#!/usr/bin/env python
"""Run the fast/default engineering test suite.

This keeps benchmark-heavy synthetic dataset tests out of the normal feedback
loop. Use `scripts/run_heavy_tests.py` when you want the richer benchmark
generation coverage as well.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
import unittest


def main() -> int:
    os.environ["PII_DISABLE_LOCAL_ENV"] = "1"
    os.environ["PII_LOCAL_LLM_ENABLED"] = "0"
    os.environ["PII_LOCAL_LLM_FILE_QA_ENABLED"] = "0"
    repo_root = Path(__file__).resolve().parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    suite = unittest.defaultTestLoader.discover("tests", pattern="test*.py")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
