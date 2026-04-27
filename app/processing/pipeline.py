"""Top-level analysis pipeline for UI jobs and benchmark runs.

This module owns the end-to-end workflow from parsed email evidence to emitted
review artifacts. The phase boundaries stay explicit so a new engineer can
trace where extraction, detection, attribution, QA review, risk scoring, and
report generation happen.
"""

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

from app.processing.pipeline_options import AnalysisPipelineOptions
from app.settings import THREAD_POOL_WORKERS
from app.models import AnalysisJobSummary, EmailAnalysisResult, ProgressUpdate, SourceExtractionMetadata
from app.processing.eml_parser import parse_eml_file
from app.processing.pipeline_file_processing import (
    append_result_json,
    error_result,
    process_attachment,
    scan_source_text,
)
from app.processing.pipeline_followup import apply_bounded_qa_followup
from app.processing.person_resolver import resolve_persons
from app.processing.risk_scorer import update_person_risk
from app.reporting.html_report import generate_html_report
from app.reporting.csv_report import generate_csv_report
from app.reporting.file_review_csv import generate_file_review_csv
from app.runtime_metadata import (
    CSV_REPORT_SCHEMA_VERSION,
    CURRENT_BUILD_ID,
    CURRENT_BUILD_LABEL,
    FILE_REVIEW_SCHEMA_VERSION,
    HTML_REPORT_SCHEMA_VERSION,
)

logger = logging.getLogger(__name__)
FILE_PROCESSING_EXECUTOR = ThreadPoolExecutor(max_workers=THREAD_POOL_WORKERS, thread_name_prefix="pii-scan")


@dataclass
class GeneratedReports:
    html_report_path: Path
    html_content: str
    csv_report_path: Path
    file_review_csv_path: Path


async def run_analysis_pipeline(
    job_id: str,
    file_paths: list[Path],
    progress_callback: Callable,
    jobs_dir: Path,
    options: AnalysisPipelineOptions | None = None,
) -> AnalysisJobSummary:
    """Run the full reviewer-facing analysis workflow for one upload job."""
    options = options or AnalysisPipelineOptions()
    logger.info(f"Starting pipeline for job {job_id} with {len(file_paths)} files")

    results_file = jobs_dir / job_id / "results.json"
    results_accumulator = await _process_eml_files(file_paths, progress_callback, results_file)

    logger.info(f"Phase 1 complete: {len(results_accumulator)} emails processed")
    await _run_file_qa(results_accumulator, progress_callback, options)
    persons = await _resolve_and_score_persons(results_accumulator, progress_callback, len(file_paths), options)
    reports = await _generate_reports(job_id, persons, results_accumulator, jobs_dir, progress_callback, len(file_paths), options)
    summary = _build_summary(job_id, persons, results_accumulator, reports, options)

    await progress_callback(
        ProgressUpdate(
            status="complete",
            processed=len(file_paths),
            total=len(file_paths),
            persons_found=len(persons),
            message="Analysis complete",
        )
    )

    return summary


def process_single_eml(file_path: Path) -> EmailAnalysisResult:
    """Process one `.eml` file into extracted sources and deterministic findings."""
    logger.debug(f"Processing EML: {file_path.name}")

    # Parse EML file
    eml_data = parse_eml_file(str(file_path))

    result = EmailAnalysisResult(
        eml_filename=file_path.name,
        from_address=eml_data.get("from_address"),
        from_name=eml_data.get("from_name"),
        to_addresses=eml_data.get("to_addresses", []),
        to_names=eml_data.get("to_names", []),
        cc_addresses=eml_data.get("cc_addresses", []),
        bcc_addresses=eml_data.get("bcc_addresses", []),
        subject=eml_data.get("subject", ""),
    )

    if eml_data.get("error"):
        result.error = eml_data["error"]
        return result

    subject = eml_data.get("subject", "").strip()
    if subject:
        scan_source_text(
            result,
            f"{file_path.name} (email subject)",
            f"Subject: {subject}",
            SourceExtractionMetadata(
                source_ref=f"{file_path.name} (email subject)",
                extraction_method="email_subject",
                parser="eml_parser",
            ),
        )

    body_text = eml_data.get("body_text", "")
    if body_text:
        scan_source_text(
            result,
            f"{file_path.name} (email body)",
            body_text,
            SourceExtractionMetadata(
                source_ref=f"{file_path.name} (email body)",
                extraction_method="email_body",
                parser="eml_parser",
            ),
        )

    for attachment in eml_data.get("attachments", []):
        process_attachment(result, file_path.name, attachment)

    logger.debug(f"Found {len(result.pii_matches)} PII matches in {file_path.name}")
    return result


async def _process_eml_files(
    file_paths: list[Path],
    progress_callback: Callable,
    results_file: Path,
) -> list[EmailAnalysisResult]:
    results: list[EmailAnalysisResult] = []
    futures = {FILE_PROCESSING_EXECUTOR.submit(process_single_eml, file_path): file_path for file_path in file_paths}
    for index, future in enumerate(as_completed(futures), start=1):
        file_path = futures[future]
        try:
            eml_result = future.result()
            append_result_json(results_file, eml_result)
        except Exception as exc:
            logger.error("Error processing %s: %s", file_path, exc)
            eml_result = error_result(file_path, exc)
        results.append(eml_result)
        await progress_callback(
            ProgressUpdate(
                status="progress",
                processed=index,
                total=len(file_paths),
                current_file=file_path.name,
                persons_found=0,
            )
        )
    return results


async def _run_file_qa(
    results: list[EmailAnalysisResult],
    progress_callback: Callable,
    options: AnalysisPipelineOptions,
) -> None:
    await progress_callback(
        ProgressUpdate(
            status="progress",
            processed=len(results),
            total=len(results),
            current_file="",
            persons_found=0,
            message="Running AI QA review",
        )
    )
    qa_helper = options.build_file_qa_helper()
    if not qa_helper.enabled:
        return

    worker_count = max(1, options.file_qa_workers)

    async def review_one(result: EmailAnalysisResult) -> tuple[EmailAnalysisResult, object]:
        review = await asyncio.to_thread(qa_helper.review_email_result, result)
        return result, review

    if worker_count == 1:
        completed = 0
        for result in results:
            reviewed_result, review = await review_one(result)
            reviewed_result.qa_review = review
            apply_bounded_qa_followup(reviewed_result)
            completed += 1
            await progress_callback(
                ProgressUpdate(
                    status="progress",
                    processed=completed,
                    total=len(results),
                    current_file=reviewed_result.eml_filename,
                    persons_found=0,
                    message="AI QA review",
                )
            )
        return

    semaphore = asyncio.Semaphore(worker_count)

    async def bounded_review(result: EmailAnalysisResult) -> tuple[EmailAnalysisResult, object]:
        async with semaphore:
            return await review_one(result)

    tasks = [asyncio.create_task(bounded_review(result)) for result in results]
    completed = 0
    for task in asyncio.as_completed(tasks):
        reviewed_result, review = await task
        reviewed_result.qa_review = review
        apply_bounded_qa_followup(reviewed_result)
        completed += 1
        await progress_callback(
            ProgressUpdate(
                status="progress",
                processed=completed,
                total=len(results),
                current_file=reviewed_result.eml_filename,
                persons_found=0,
                message="AI QA review",
            )
        )


async def _resolve_and_score_persons(
    results: list[EmailAnalysisResult],
    progress_callback: Callable,
    total_files: int,
    options: AnalysisPipelineOptions,
) -> list:
    await progress_callback(
        ProgressUpdate(
            status="progress",
            processed=len(results),
            total=total_files,
            current_file="",
            persons_found=0,
            message="Resolving affected persons",
        )
    )
    if options.attribution_llm_helper is not None:
        persons = resolve_persons(results, llm_helper=options.attribution_llm_helper)
    else:
        persons = resolve_persons(results)
    logger.info("Phase 2 complete: %s persons identified", len(persons))

    for person in persons:
        update_person_risk(person)
    logger.info("Phase 3 complete: Risk scores calculated")
    return persons


async def _generate_reports(
    job_id: str,
    persons: list,
    results: list[EmailAnalysisResult],
    jobs_dir: Path,
    progress_callback: Callable,
    total_files: int,
    options: AnalysisPipelineOptions,
) -> GeneratedReports:
    await progress_callback(
        ProgressUpdate(
            status="progress",
            processed=total_files,
            total=total_files,
            current_file="",
            persons_found=len(persons),
            message="Generating HTML and CSV reports",
        )
    )

    html_report_path, html_content = generate_html_report(job_id, persons, results, jobs_dir)
    csv_report_path = generate_csv_report(job_id, persons, jobs_dir)
    file_review_csv_path = generate_file_review_csv(job_id, results, jobs_dir)
    if options.file_qa_enabled and not file_review_csv_path.exists():
        raise RuntimeError(
            "AI QA review export was expected but file_review.csv was not generated. "
            "Restart the web server and rerun the job."
        )
    logger.info("Phase 4 complete: Reports generated")
    return GeneratedReports(
        html_report_path=html_report_path,
        html_content=html_content,
        csv_report_path=csv_report_path,
        file_review_csv_path=file_review_csv_path,
    )


def _build_summary(
    job_id: str,
    persons: list,
    results: list[EmailAnalysisResult],
    reports: GeneratedReports,
    options: AnalysisPipelineOptions,
) -> AnalysisJobSummary:
    """Build the job summary consumed by the UI and report download endpoints."""
    return AnalysisJobSummary(
        job_id=job_id,
        total_files_processed=len(results),
        total_persons_affected=len(persons),
        persons_high_risk=sum(1 for person in persons if person.highest_risk_level in ("CRITICAL", "HIGH")),
        persons_medium_risk=sum(1 for person in persons if person.highest_risk_level == "MEDIUM"),
        persons_notification_required=sum(1 for person in persons if person.notification_required),
        persons=persons,
        html_report=str(reports.html_report_path),
        html_content=reports.html_content,
        csv_report=str(reports.csv_report_path),
        file_review_csv=str(reports.file_review_csv_path),
        file_review_expected=options.file_qa_enabled,
        file_review_available=reports.file_review_csv_path.exists(),
        build_id=CURRENT_BUILD_ID,
        build_label=CURRENT_BUILD_LABEL,
        html_report_schema_version=HTML_REPORT_SCHEMA_VERSION,
        csv_report_schema_version=CSV_REPORT_SCHEMA_VERSION,
        file_review_schema_version=FILE_REVIEW_SCHEMA_VERSION,
        files_ai_reviewed=sum(1 for result in results if result.qa_review and result.qa_review.reviewed),
        files_needing_human_review=sum(
            1 for result in results if result.qa_review and result.qa_review.needs_human_review
        ),
        files_with_followup_matches=sum(
            1 for result in results if result.qa_review and result.qa_review.followup_match_count > 0
        ),
        files_with_low_confidence_ocr=sum(
            1 for result in results if any(metadata.low_confidence_ocr for metadata in result.source_extractions.values())
        ),
    )


def _apply_bounded_qa_followup(result: EmailAnalysisResult) -> None:
    """Compatibility wrapper for tests and any legacy private imports."""
    apply_bounded_qa_followup(result)


def shutdown_pipeline_executors() -> None:
    """Release shared executors during process shutdown."""
    FILE_PROCESSING_EXECUTOR.shutdown(wait=False, cancel_futures=True)
