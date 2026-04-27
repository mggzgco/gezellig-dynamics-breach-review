from __future__ import annotations

import json
import shutil
from pathlib import Path

from app.benchmarking.attachments import _set_single_header
from app.benchmarking.fixtures import (
    BENCHMARK_SEED,
    DEFAULT_BENCHMARK_FILE_COUNT,
    DEFAULT_BENCHMARK_PROFILE,
    GROUND_TRUTH_FILENAME,
    GROUND_TRUTH_SUMMARY_FILENAME,
    REALWORLD_V2_PROFILE,
    REALWORLD_V3_PROFILE,
    REALWORLD_V4_PROFILE,
    WORK_DOMAINS,
    _make_person,
)
from app.benchmarking.ground_truth import BenchmarkDataset, BenchmarkFile
from app.benchmarking.scenarios import _profile_dataset_metadata, _scenario_for_profile


def _summary_markdown(dataset: BenchmarkDataset) -> str:
    summary = dataset.summary()
    lines = [
        "# Benchmark Ground Truth Summary",
        "",
        f"- Dataset: {dataset.name}",
        f"- Seed: {dataset.seed}",
        f"- Total files: {summary['total_files']}",
        f"- Files with PII: {summary['files_with_pii']}",
        f"- Files without PII: {summary['files_without_pii']}",
        f"- Total expected findings: {summary['total_findings']}",
        f"- Files expected to need human review: {summary['expected_human_review_files']}",
        "",
        "## Type Coverage",
        "",
        "| PII Type | Findings | Files |",
        "|---|---:|---:|",
    ]
    type_counts = summary["type_counts"]
    type_file_counts = summary["type_file_counts"]
    for pii_type in sorted(type_counts):
        lines.append(f"| {pii_type} | {type_counts[pii_type]} | {type_file_counts.get(pii_type, 0)} |")
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- This corpus is synthetic but formatted as realistic operational email and attachment traffic.",
            "- Ground truth is stored in `ground_truth.json`; this markdown file is only a readable summary.",
            "- Attachments are real parseable files and include TXT, CSV, DOCX, XLSX, RTF, ZIP, and nested EML examples.",
            "- Negative controls intentionally include dates, service contacts, ticket IDs, and infrastructure IPs to measure false positives.",
        ]
    )
    return "\n".join(lines) + "\n"


def generate_benchmark_dataset(
    output_dir: Path,
    *,
    file_count: int = DEFAULT_BENCHMARK_FILE_COUNT,
    start_index: int = 1,
    seed: int = BENCHMARK_SEED,
    profile: str = DEFAULT_BENCHMARK_PROFILE,
    clean: bool = True,
) -> BenchmarkDataset:
    if file_count <= 0:
        raise ValueError("file_count must be positive.")
    if start_index <= 0:
        raise ValueError("start_index must be positive.")

    if clean and output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    benchmark_files: list[BenchmarkFile] = []
    dataset_name, dataset_description = _profile_dataset_metadata(profile)

    for relative_index, index in enumerate(range(start_index, start_index + file_count), start=1):
        message, benchmark_file = _scenario_for_profile(
            profile,
            index,
            seed,
            relative_index=relative_index,
            total_files=file_count,
        )
        _set_single_header(message, "From", f"notices@{WORK_DOMAINS[index % len(WORK_DOMAINS)]}")
        _set_single_header(message, "To", _make_person(index + 900, seed).work_email)
        eml_path = output_dir / benchmark_file.eml_filename
        eml_path.write_bytes(message.as_bytes())
        benchmark_files.append(benchmark_file)

    dataset = BenchmarkDataset.new(
        name=dataset_name,
        description=dataset_description,
        seed=seed,
        files=benchmark_files,
    )
    dataset.save(output_dir / GROUND_TRUTH_FILENAME)
    (output_dir / GROUND_TRUTH_SUMMARY_FILENAME).write_text(_summary_markdown(dataset), encoding="utf-8")
    return dataset


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Generate the synthetic PII breach benchmark dataset.")
    parser.add_argument("output_dir", type=Path, help="Directory where the 300-file benchmark should be written.")
    parser.add_argument("--seed", type=int, default=BENCHMARK_SEED, help="Random seed for deterministic generation.")
    parser.add_argument("--file-count", type=int, default=DEFAULT_BENCHMARK_FILE_COUNT, help="Number of benchmark emails to generate. Defaults to 300.")
    parser.add_argument("--start-index", type=int, default=1, help="Starting email index for generated slices. Defaults to 1.")
    parser.add_argument(
        "--profile",
        type=str,
        default=DEFAULT_BENCHMARK_PROFILE,
        choices=[DEFAULT_BENCHMARK_PROFILE, REALWORLD_V2_PROFILE, REALWORLD_V3_PROFILE, REALWORLD_V4_PROFILE],
        help="Benchmark profile to generate.",
    )
    parser.add_argument("--no-clean", action="store_true", help="Do not remove the output directory before generation.")
    args = parser.parse_args()

    dataset = generate_benchmark_dataset(
        args.output_dir,
        file_count=args.file_count,
        start_index=args.start_index,
        seed=args.seed,
        profile=args.profile,
        clean=not args.no_clean,
    )
    print(json.dumps(dataset.summary(), indent=2))


if __name__ == "__main__":
    main()
