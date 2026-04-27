"""Benchmark scoring harness for generated analyzer datasets."""

from __future__ import annotations

import asyncio
import csv
import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Iterable, Optional
from uuid import uuid4

from app.benchmarking.ground_truth import BenchmarkDataset, ExpectedFinding
from app.models import AnalysisJobSummary
from app.pii_catalog import PII_CATALOG
from app.processing.entity_resolution_utils import extract_name_from_email, normalize_name
from app.processing.local_llm_attribution import LocalLLMAttributionHelper
from app.processing.local_llm_file_qa import LocalLLMFileQAHelper
from app.processing.pipeline import process_single_eml, run_analysis_pipeline
from app.processing.pipeline_options import AnalysisPipelineOptions
from app.reporting.csv_report import HEADER_MAPPING


GROUND_TRUTH_FILENAME = "ground_truth.json"
EVALUATION_JSON_FILENAME = "evaluation_summary.json"
EVALUATION_MD_FILENAME = "evaluation_summary.md"

HUMAN_HEADER_TO_INTERNAL = {human: internal for internal, human in HEADER_MAPPING.items()}
KNOWN_PII_TYPES = sorted({pattern.name for pattern in PII_CATALOG})


@dataclass
class MetricCounts:
    expected: int = 0
    detected: int = 0
    true_positive: int = 0
    false_positive: int = 0
    false_negative: int = 0

    @property
    def precision(self) -> float:
        if self.detected == 0:
            return 1.0 if self.expected == 0 else 0.0
        return self.true_positive / self.detected

    @property
    def recall(self) -> float:
        if self.expected == 0:
            return 1.0
        return self.true_positive / self.expected

    def to_dict(self) -> dict[str, Any]:
        return {
            "expected": self.expected,
            "detected": self.detected,
            "true_positive": self.true_positive,
            "false_positive": self.false_positive,
            "false_negative": self.false_negative,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
        }


@dataclass
class ReviewMetrics:
    expected_review_files: int = 0
    flagged_review_files: int = 0
    true_positive: int = 0
    false_positive: int = 0
    false_negative: int = 0

    @property
    def precision(self) -> float:
        if self.flagged_review_files == 0:
            return 1.0 if self.expected_review_files == 0 else 0.0
        return self.true_positive / self.flagged_review_files

    @property
    def recall(self) -> float:
        if self.expected_review_files == 0:
            return 1.0
        return self.true_positive / self.expected_review_files

    def to_dict(self) -> dict[str, Any]:
        return {
            "expected_review_files": self.expected_review_files,
            "flagged_review_files": self.flagged_review_files,
            "true_positive": self.true_positive,
            "false_positive": self.false_positive,
            "false_negative": self.false_negative,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
        }


@dataclass
class EndToEndEvaluation:
    report_job_id: str
    file_qa_enabled: bool
    attribution_llm_enabled: bool
    report_file_type: MetricCounts
    report_owner_file_type: MetricCounts
    review_metrics: ReviewMetrics
    files_with_followup_matches: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_job_id": self.report_job_id,
            "file_qa_enabled": self.file_qa_enabled,
            "attribution_llm_enabled": self.attribution_llm_enabled,
            "report_file_type": self.report_file_type.to_dict(),
            "report_owner_file_type": self.report_owner_file_type.to_dict(),
            "review_metrics": self.review_metrics.to_dict(),
            "files_with_followup_matches": self.files_with_followup_matches,
        }


@dataclass
class FileEvaluation:
    eml_filename: str
    expected_count: int
    detected_count: int
    true_positive: int
    false_positive: int
    false_negative: int
    expected_missing: list[dict[str, str]] = field(default_factory=list)
    unexpected_findings: list[dict[str, str]] = field(default_factory=list)
    ai_reviewed: bool = False
    ai_status: str = "not_run"
    ai_needs_human_review: bool = False
    ai_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EvaluationSummary:
    dataset_name: str
    dataset_dir: str
    evaluated_at: str
    deterministic_findings: MetricCounts
    by_type: dict[str, MetricCounts]
    files: list[FileEvaluation]
    files_with_missed_findings: list[str]
    files_with_false_positives: list[str]
    ai_reviewed_files: list[str]
    ai_escalated_files: list[str]
    expected_human_review_files: list[str]
    ai_caught_expected_review_files: list[str]
    end_to_end: Optional[EndToEndEvaluation] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_name": self.dataset_name,
            "dataset_dir": self.dataset_dir,
            "evaluated_at": self.evaluated_at,
            "deterministic_findings": self.deterministic_findings.to_dict(),
            "by_type": {key: metric.to_dict() for key, metric in sorted(self.by_type.items())},
            "files": [item.to_dict() for item in self.files],
            "files_with_missed_findings": self.files_with_missed_findings,
            "files_with_false_positives": self.files_with_false_positives,
            "ai_reviewed_files": self.ai_reviewed_files,
            "ai_escalated_files": self.ai_escalated_files,
            "expected_human_review_files": self.expected_human_review_files,
            "ai_caught_expected_review_files": self.ai_caught_expected_review_files,
            "end_to_end": self.end_to_end.to_dict() if self.end_to_end else None,
        }


def _finding_key(finding: ExpectedFinding) -> tuple[str, str, str]:
    return finding.counter_key()


def _actual_key(match) -> tuple[str, str, str]:
    return (match.source_ref, match.pii_type, match.normalized_value)


def _count_true_positives(expected_counter: Counter, actual_counter: Counter) -> int:
    shared_keys = set(expected_counter) | set(actual_counter)
    return sum(min(expected_counter[key], actual_counter[key]) for key in shared_keys)


def evaluate_benchmark(
    dataset_dir: Path,
    *,
    run_ai_qa: bool = False,
    run_attribution_llm: bool = False,
    force_ai_review_all: bool = False,
    include_end_to_end: bool = True,
) -> EvaluationSummary:
    """Score one benchmark dataset against deterministic findings and optional AI QA."""
    dataset_path = dataset_dir / GROUND_TRUTH_FILENAME
    dataset = BenchmarkDataset.load(dataset_path)
    available_files = {path.name for path in dataset_dir.glob("*.eml")}
    if available_files:
        dataset.files = [item for item in dataset.files if item.eml_filename in available_files]
    risk_levels = {pattern.name: pattern.risk_level for pattern in PII_CATALOG}

    deterministic_totals = MetricCounts()
    by_type: dict[str, MetricCounts] = defaultdict(MetricCounts)
    file_evaluations: list[FileEvaluation] = []
    files_with_missed_findings: list[str] = []
    files_with_false_positives: list[str] = []
    ai_reviewed_files: list[str] = []
    ai_escalated_files: list[str] = []
    expected_human_review_files: list[str] = [item.eml_filename for item in dataset.files if item.expected_human_review]
    ai_caught_expected_review_files: list[str] = []

    qa_helper = LocalLLMFileQAHelper(enabled=run_ai_qa, review_all_files=force_ai_review_all)

    for benchmark_file in dataset.files:
        result = process_single_eml(dataset_dir / benchmark_file.eml_filename)
        if run_ai_qa and qa_helper.enabled:
            result.qa_review = qa_helper.review_email_result(result)

        expected_counter = Counter(_finding_key(finding) for finding in benchmark_file.expected_findings)
        actual_counter = Counter(_actual_key(match) for match in result.pii_matches)
        true_positive = _count_true_positives(expected_counter, actual_counter)
        false_negative = sum(expected_counter.values()) - true_positive
        false_positive = sum(actual_counter.values()) - true_positive

        deterministic_totals.expected += sum(expected_counter.values())
        deterministic_totals.detected += sum(actual_counter.values())
        deterministic_totals.true_positive += true_positive
        deterministic_totals.false_negative += false_negative
        deterministic_totals.false_positive += false_positive

        expected_missing: list[dict[str, str]] = []
        unexpected_findings: list[dict[str, str]] = []

        for key in set(expected_counter) | set(actual_counter):
            source_ref, pii_type, normalized_value = key
            shared = min(expected_counter[key], actual_counter[key])
            missing = expected_counter[key] - shared
            unexpected = actual_counter[key] - shared

            metric = by_type[pii_type]
            metric.expected += expected_counter[key]
            metric.detected += actual_counter[key]
            metric.true_positive += shared
            metric.false_negative += max(0, missing)
            metric.false_positive += max(0, unexpected)

            if missing > 0:
                expected_missing.append(
                    {
                        "pii_type": pii_type,
                        "source_ref": source_ref,
                        "normalized_value": normalized_value,
                        "count": str(missing),
                        "risk_level": risk_levels.get(pii_type, "UNKNOWN"),
                    }
                )

            if unexpected > 0:
                unexpected_findings.append(
                    {
                        "pii_type": pii_type,
                        "source_ref": source_ref,
                        "normalized_value": normalized_value,
                        "count": str(unexpected),
                        "risk_level": risk_levels.get(pii_type, "UNKNOWN"),
                    }
                )

        if expected_missing:
            files_with_missed_findings.append(benchmark_file.eml_filename)
        if unexpected_findings:
            files_with_false_positives.append(benchmark_file.eml_filename)

        ai_reviewed = bool(result.qa_review and result.qa_review.reviewed)
        ai_needs_human_review = bool(result.qa_review and result.qa_review.needs_human_review)
        ai_status = result.qa_review.status if result.qa_review else "not_run"
        ai_reason = result.qa_review.reason if result.qa_review else ""
        if ai_reviewed:
            ai_reviewed_files.append(benchmark_file.eml_filename)
        if ai_needs_human_review:
            ai_escalated_files.append(benchmark_file.eml_filename)
        if benchmark_file.expected_human_review and ai_needs_human_review:
            ai_caught_expected_review_files.append(benchmark_file.eml_filename)

        file_evaluations.append(
            FileEvaluation(
                eml_filename=benchmark_file.eml_filename,
                expected_count=sum(expected_counter.values()),
                detected_count=sum(actual_counter.values()),
                true_positive=true_positive,
                false_positive=false_positive,
                false_negative=false_negative,
                expected_missing=sorted(expected_missing, key=lambda item: (item["pii_type"], item["source_ref"])),
                unexpected_findings=sorted(unexpected_findings, key=lambda item: (item["pii_type"], item["source_ref"])),
                ai_reviewed=ai_reviewed,
                ai_status=ai_status,
                ai_needs_human_review=ai_needs_human_review,
                ai_reason=ai_reason,
            )
        )

    from datetime import datetime, timezone

    end_to_end = (
        _evaluate_end_to_end(
            dataset_dir,
            dataset,
            run_ai_qa,
            run_attribution_llm=run_attribution_llm,
            force_ai_review_all=force_ai_review_all,
        )
        if include_end_to_end
        else None
    )

    return EvaluationSummary(
        dataset_name=dataset.name,
        dataset_dir=str(dataset_dir),
        evaluated_at=datetime.now(timezone.utc).isoformat(),
        deterministic_findings=deterministic_totals,
        by_type=dict(by_type),
        files=file_evaluations,
        files_with_missed_findings=files_with_missed_findings,
        files_with_false_positives=files_with_false_positives,
        ai_reviewed_files=ai_reviewed_files,
        ai_escalated_files=ai_escalated_files,
        expected_human_review_files=expected_human_review_files,
        ai_caught_expected_review_files=ai_caught_expected_review_files,
        end_to_end=end_to_end,
    )


def save_evaluation(summary: EvaluationSummary, output_dir: Path) -> None:
    """Persist machine-readable and markdown benchmark summaries."""
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / EVALUATION_JSON_FILENAME).write_text(json.dumps(summary.to_dict(), indent=2), encoding="utf-8")
    (output_dir / EVALUATION_MD_FILENAME).write_text(render_evaluation_markdown(summary), encoding="utf-8")


def render_evaluation_markdown(summary: EvaluationSummary) -> str:
    """Render a concise markdown summary for humans reviewing benchmark output."""
    lines = [
        "# Benchmark Evaluation Summary",
        "",
        f"- Dataset: {summary.dataset_name}",
        f"- Dataset dir: `{summary.dataset_dir}`",
        f"- Evaluated at: {summary.evaluated_at}",
        f"- Direct deterministic finding precision: {summary.deterministic_findings.precision:.1%}",
        f"- Direct deterministic finding recall: {summary.deterministic_findings.recall:.1%}",
        f"- Files with missed findings: {len(summary.files_with_missed_findings)}",
        f"- Files with false positives: {len(summary.files_with_false_positives)}",
        f"- AI-reviewed files: {len(summary.ai_reviewed_files)}",
        f"- AI-escalated files: {len(summary.ai_escalated_files)}",
        f"- Expected human-review files caught by AI: {len(summary.ai_caught_expected_review_files)} / {len(summary.expected_human_review_files)}",
        "",
        "## By Type",
        "",
        "| PII Type | Expected | Detected | TP | FP | FN | Precision | Recall |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for pii_type, metric in sorted(summary.by_type.items()):
        lines.append(
            f"| {pii_type} | {metric.expected} | {metric.detected} | {metric.true_positive} | {metric.false_positive} | {metric.false_negative} | {metric.precision:.1%} | {metric.recall:.1%} |"
        )

    if summary.end_to_end:
        lines.extend(
            [
                "",
                "## End-to-End Report Scoring",
                "",
                "- These metrics are from the full pipeline and emitted report artifacts, not the direct scanner alone.",
                f"- File QA enabled: {'yes' if summary.end_to_end.file_qa_enabled else 'no'}",
                f"- Attribution LLM enabled: {'yes' if summary.end_to_end.attribution_llm_enabled else 'no'}",
                f"- Report file/type precision: {summary.end_to_end.report_file_type.precision:.1%}",
                f"- Report file/type recall: {summary.end_to_end.report_file_type.recall:.1%}",
                f"- Report owner-aware precision: {summary.end_to_end.report_owner_file_type.precision:.1%}",
                f"- Report owner-aware recall: {summary.end_to_end.report_owner_file_type.recall:.1%}",
                f"- Review-escalation precision: {summary.end_to_end.review_metrics.precision:.1%}",
                f"- Review-escalation recall: {summary.end_to_end.review_metrics.recall:.1%}",
                f"- Files with QA follow-up matches: {summary.end_to_end.files_with_followup_matches}",
            ]
        )

    if summary.ai_reviewed_files:
        lines.extend(
            [
                "",
                "## AI Review",
                "",
                f"- AI-reviewed files: {', '.join(summary.ai_reviewed_files[:20])}" + (" ..." if len(summary.ai_reviewed_files) > 20 else ""),
                f"- AI-escalated files: {', '.join(summary.ai_escalated_files[:20])}" + (" ..." if len(summary.ai_escalated_files) > 20 else ""),
            ]
        )

    if summary.files_with_missed_findings:
        lines.extend(
            [
                "",
                "## Error Hotspots",
                "",
                f"- Missed findings present in: {', '.join(summary.files_with_missed_findings[:20])}" + (" ..." if len(summary.files_with_missed_findings) > 20 else ""),
                f"- False positives present in: {', '.join(summary.files_with_false_positives[:20])}" + (" ..." if len(summary.files_with_false_positives) > 20 else ""),
            ]
        )

    return "\n".join(lines) + "\n"


def _evaluate_end_to_end(
    dataset_dir: Path,
    dataset: BenchmarkDataset,
    run_ai_qa: bool,
    *,
    run_attribution_llm: bool,
    force_ai_review_all: bool,
) -> EndToEndEvaluation:
    summary, report_rows, file_review_rows = _run_end_to_end_pipeline(
        dataset_dir,
        run_ai_qa=run_ai_qa,
        run_attribution_llm=run_attribution_llm,
        force_ai_review_all=force_ai_review_all,
    )

    expected_file_types = {
        (benchmark_file.eml_filename, finding.pii_type)
        for benchmark_file in dataset.files
        for finding in benchmark_file.expected_findings
    }
    expected_owner_file_types = {
        (benchmark_file.eml_filename, finding.pii_type, finding.owner_key())
        for benchmark_file in dataset.files
        for finding in benchmark_file.expected_findings
        if finding.owner_key()
    }

    actual_file_types = set()
    actual_owner_file_types = set()
    for row in report_rows:
        current_source_file = (row.get("current_source_file") or "").strip()
        if not current_source_file:
            continue
        owner_key = _owner_key_from_report_row(row)
        for pii_type in KNOWN_PII_TYPES:
            if str(row.get(pii_type, "")).strip().upper() == "Y":
                actual_file_types.add((current_source_file, pii_type))
                actual_owner_file_types.add((current_source_file, pii_type, owner_key))

    expected_review_files = {item.eml_filename for item in dataset.files if item.expected_human_review}
    actual_review_files = {
        row["eml_filename"]
        for row in file_review_rows
        if str(row.get("qa_needs_human_review", "")).strip().upper() == "Y"
    }

    review_metrics = ReviewMetrics(
        expected_review_files=len(expected_review_files),
        flagged_review_files=len(actual_review_files),
        true_positive=len(expected_review_files & actual_review_files),
        false_positive=len(actual_review_files - expected_review_files),
        false_negative=len(expected_review_files - actual_review_files),
    )

    return EndToEndEvaluation(
        report_job_id=summary.job_id,
        file_qa_enabled=run_ai_qa,
        attribution_llm_enabled=run_attribution_llm,
        report_file_type=_score_set_metrics(expected_file_types, actual_file_types),
        report_owner_file_type=_score_set_metrics(expected_owner_file_types, actual_owner_file_types),
        review_metrics=review_metrics,
        files_with_followup_matches=sum(
            1
            for row in file_review_rows
            if int(str(row.get("qa_followup_match_count", "0") or "0")) > 0
        ),
    )


def _score_set_metrics(expected: set[tuple], actual: set[tuple]) -> MetricCounts:
    return MetricCounts(
        expected=len(expected),
        detected=len(actual),
        true_positive=len(expected & actual),
        false_positive=len(actual - expected),
        false_negative=len(expected - actual),
    )


def _run_end_to_end_pipeline(
    dataset_dir: Path,
    *,
    run_ai_qa: bool,
    run_attribution_llm: bool,
    force_ai_review_all: bool,
) -> tuple[AnalysisJobSummary, list[dict[str, str]], list[dict[str, str]]]:
    async def _progress_noop(_progress) -> None:
        return None

    file_paths = sorted(dataset_dir.glob("email_*.eml"))
    file_qa_helper_factory = None
    if run_ai_qa and force_ai_review_all:
        file_qa_helper_factory = lambda: LocalLLMFileQAHelper(enabled=True, review_all_files=True)

    options = AnalysisPipelineOptions(
        file_qa_enabled=run_ai_qa,
        file_qa_helper_factory=file_qa_helper_factory,
        attribution_llm_helper=LocalLLMAttributionHelper(enabled=run_attribution_llm),
    )

    with TemporaryDirectory() as temp_dir:
        jobs_dir = Path(temp_dir)
        job_id = f"benchmark-e2e-{uuid4().hex[:8]}"
        summary = asyncio.run(
            run_analysis_pipeline(
                job_id,
                file_paths,
                _progress_noop,
                jobs_dir,
                options=options,
            )
        )

        report_rows = _read_report_csv(Path(summary.csv_report))
        file_review_rows = _read_file_review_csv(Path(summary.file_review_csv))
        return summary, report_rows, file_review_rows


def _read_report_csv(report_path: Path) -> list[dict[str, str]]:
    with report_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = []
        for row in reader:
            normalized = {HUMAN_HEADER_TO_INTERNAL.get(key, key): value for key, value in row.items()}
            rows.append(normalized)
        return rows


def _read_file_review_csv(report_path: Path) -> list[dict[str, str]]:
    with report_path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _owner_key_from_report_row(row: dict[str, str]) -> str:
    canonical_name = (row.get("canonical_name") or "").strip()
    canonical_email = (row.get("canonical_email") or "").strip().lower()
    entity_type = (row.get("entity_type") or "").strip().upper()

    if canonical_name:
        return normalize_name(canonical_name)
    if canonical_email:
        return normalize_name(extract_name_from_email(canonical_email)) or canonical_email
    return entity_type or "UNATTRIBUTED"


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Evaluate the PII analyzer against a benchmark dataset.")
    parser.add_argument("dataset_dir", type=Path, help="Benchmark dataset directory containing .eml files and ground_truth.json.")
    parser.add_argument("--with-ai-qa", action="store_true", help="Run file-level local AI QA during evaluation.")
    parser.add_argument(
        "--with-ai-attribution",
        action="store_true",
        help="Enable local-LLM attribution during end-to-end evaluation.",
    )
    parser.add_argument(
        "--force-ai-review-all",
        action="store_true",
        help="Benchmark the AI reviewer in forced-review mode instead of using production gating.",
    )
    parser.add_argument("--skip-end-to-end", action="store_true", help="Skip report-layer end-to-end evaluation.")
    parser.add_argument("--output-dir", type=Path, default=None, help="Directory where evaluation output should be written.")
    args = parser.parse_args()

    summary = evaluate_benchmark(
        args.dataset_dir,
        run_ai_qa=args.with_ai_qa,
        run_attribution_llm=args.with_ai_attribution,
        force_ai_review_all=args.force_ai_review_all,
        include_end_to_end=not args.skip_end_to_end,
    )
    output_dir = args.output_dir or args.dataset_dir
    save_evaluation(summary, output_dir)
    print(json.dumps(summary.to_dict()["deterministic_findings"], indent=2))
    if summary.end_to_end:
        print(json.dumps(summary.end_to_end.to_dict(), indent=2))
    print(f"AI reviewed files: {len(summary.ai_reviewed_files)}")


if __name__ == "__main__":
    main()
