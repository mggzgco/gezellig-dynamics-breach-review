from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from app.pii_catalog import PII_CATALOG


def _default_normalizer(value: str) -> str:
    return " ".join(value.strip().split())


_NORMALIZER_BY_TYPE: dict[str, Callable[[str], str]] = {}
for pattern in PII_CATALOG:
    if pattern.normalizer:
        _NORMALIZER_BY_TYPE[pattern.name] = pattern.normalizer


def normalize_ground_truth_value(pii_type: str, raw_value: str) -> str:
    normalizer = _NORMALIZER_BY_TYPE.get(pii_type, _default_normalizer)
    return normalizer(raw_value)


@dataclass
class ExpectedFinding:
    pii_type: str
    raw_value: str
    source_ref: str
    normalized_value: str = ""
    location_kind: str = "body"
    entity_name: Optional[str] = None
    attachment_filename: Optional[str] = None
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.normalized_value:
            self.normalized_value = normalize_ground_truth_value(self.pii_type, self.raw_value)

    def counter_key(self) -> tuple[str, str, str]:
        return (self.source_ref, self.pii_type, self.normalized_value)

    def owner_key(self) -> str:
        return _default_normalizer((self.entity_name or "").upper()) if self.entity_name else ""


@dataclass
class BenchmarkFile:
    eml_filename: str
    scenario_id: str
    subject: str
    contains_pii: bool
    expected_findings: list[ExpectedFinding] = field(default_factory=list)
    attachments: list[str] = field(default_factory=list)
    expected_human_review: bool = False
    notes: str = ""

    def __post_init__(self) -> None:
        self.contains_pii = bool(self.expected_findings)


@dataclass
class BenchmarkDataset:
    schema_version: int
    name: str
    description: str
    seed: int
    created_at: str
    files: list[BenchmarkFile] = field(default_factory=list)

    @classmethod
    def new(
        cls,
        *,
        name: str,
        description: str,
        seed: int,
        files: list[BenchmarkFile],
    ) -> "BenchmarkDataset":
        return cls(
            schema_version=1,
            name=name,
            description=description,
            seed=seed,
            created_at=datetime.now(timezone.utc).isoformat(),
            files=files,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "name": self.name,
            "description": self.description,
            "seed": self.seed,
            "created_at": self.created_at,
            "summary": self.summary(),
            "files": [asdict(file) for file in self.files],
        }

    def save(self, output_path: Path) -> None:
        output_path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, input_path: Path) -> "BenchmarkDataset":
        payload = json.loads(input_path.read_text(encoding="utf-8"))
        files = []
        for item in payload.get("files", []):
            findings = [ExpectedFinding(**finding) for finding in item.get("expected_findings", [])]
            files.append(
                BenchmarkFile(
                    eml_filename=item["eml_filename"],
                    scenario_id=item["scenario_id"],
                    subject=item["subject"],
                    contains_pii=item.get("contains_pii", bool(findings)),
                    expected_findings=findings,
                    attachments=item.get("attachments", []),
                    expected_human_review=item.get("expected_human_review", False),
                    notes=item.get("notes", ""),
                )
            )
        return cls(
            schema_version=payload.get("schema_version", 1),
            name=payload.get("name", "benchmark"),
            description=payload.get("description", ""),
            seed=payload.get("seed", 0),
            created_at=payload.get("created_at", ""),
            files=files,
        )

    def summary(self) -> dict[str, Any]:
        counts = Counter()
        files_by_type: dict[str, set[str]] = {}
        for benchmark_file in self.files:
            for finding in benchmark_file.expected_findings:
                counts[finding.pii_type] += 1
                files_by_type.setdefault(finding.pii_type, set()).add(benchmark_file.eml_filename)

        return {
            "total_files": len(self.files),
            "files_with_pii": sum(1 for item in self.files if item.expected_findings),
            "files_without_pii": sum(1 for item in self.files if not item.expected_findings),
            "total_findings": sum(counts.values()),
            "type_counts": dict(sorted(counts.items())),
            "type_file_counts": {key: len(value) for key, value in sorted(files_by_type.items())},
            "expected_human_review_files": sum(1 for item in self.files if item.expected_human_review),
        }
