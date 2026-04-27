# Architecture Map

This repo is organized around one review workflow: ingest email evidence, detect
candidate PII, attribute findings to entities, score risk, and emit reviewer-
friendly reports.

## Entry Points

- `run.py`
  Starts the local web server with startup sanity checks.
- `app/main.py`
  Builds the FastAPI app, mounts routers, and owns lifecycle tasks.
- `scripts/evaluate_benchmark.py`
  Runs the analyzer against a benchmark corpus and writes evaluation summaries.

## Request Flow

1. Uploads enter through `app/api/upload.py`.
   Mixed batches with unsupported files are rejected up front instead of silently skipping invalid inputs.
2. Job status and artifacts flow through `app/api/jobs.py` and `app/api/reports.py`.
3. The core work happens in `app/processing/pipeline.py`.
4. Reports are emitted by `app/reporting/*`.

## Processing Layers

### Parsing and extraction

- `app/processing/eml_parser.py`
  Parses `.eml` messages into structured analysis inputs.
- `app/processing/attachment_handler.py`
  Routes attachments to the correct extractor and records extraction-quality metadata.
- `app/processing/extractors/*`
  Extracts normalized text from TXT, CSV, DOCX, XLSX, PDF, image, ZIP, and nested email sources.
- `app/processing/extractors/ocr_layout.py`
  Runs local Tesseract TSV OCR and rebuilds line-preserving text plus OCR confidence signals.

### Detection

- `app/processing/pii_engine.py`
  Applies the ordered PII catalog to normalized text and scores matches.
- `app/pii_catalog.py`
  Concrete ordered registry of PII rules assembled from domain modules.
- `app/pii_catalog_government.py`
  Government and public-sector identifier rules.
- `app/pii_catalog_financial.py`
  Financial identifier rules.
- `app/pii_catalog_health.py`
  Healthcare and clinical rules.
- `app/pii_catalog_personal.py`
  Contact, identity, location, vehicle, and online identifier rules.
- `app/pii_core.py`
  Compatibility facade for rule plumbing.
- `app/pii_keywords.py`
  Keyword-pattern compilation.
- `app/pii_normalization.py`
  Value normalization helpers.
- `app/pii_validation.py`
  Checksums, structural validators, and DOB parsing.
- `app/pii_match_filters.py`
  Context and false-positive suppression filters.
- `app/pii_pattern_types.py`
  `PIIPattern` data model.

### Attribution

- `app/processing/entity_resolver.py`
  High-level orchestration for entity resolution.
- `app/processing/entity_resolution_models.py`
  Attribution-side data classes.
- `app/processing/entity_resolution_utils.py`
  Shared participant/name/entity helpers.
- `app/processing/entity_resolution_extraction.py`
  Block segmentation and entity-anchor extraction.
- `app/processing/entity_resolution_attribution.py`
  Deterministic scoring and fallback attribution.
- `app/processing/entity_resolution_llm.py`
  Local-LLM ambiguity resolution only.
- `app/processing/local_llm_attribution.py`
  Structured local-LLM attribution client.
- `app/processing/local_llm_file_qa.py`
  File-level QA review client with selective triggering based on risk, extraction uncertainty, and record-like attachments.
- `app/processing/local_llm_common.py`
  Shared local-LLM transport and response parsing.

### Risk and output

- `app/processing/risk_scorer.py`
  Risk aggregation and notification-oriented scoring.
- `app/reporting/html_report.py`
  HTML report view-model assembly.
- `app/reporting/templates/report.html.j2`
  HTML report template.
- `app/reporting/csv_report.py`
  Main reviewer CSV export.
- `app/reporting/file_review_csv.py`
  Per-file QA export.

## Benchmarking

- `app/benchmarking/fixtures.py`
  Synthetic people, values, and shared benchmark constants.
- `app/benchmarking/attachments.py`
  Attachment and nested-email builders.
- `app/benchmarking/scenarios.py`
  Scenario-specific email/attachment assembly.
- `app/benchmarking/generator.py`
  Dataset writing and summary generation.
- `app/benchmarking/evaluator.py`
  Benchmark scoring against `ground_truth.json`, including report-layer and owner-aware evaluation.

## Public Configuration Surface

- `app/settings.py`
  Runtime settings and environment-driven toggles.
- `app/config.py`
  Backward-compatible facade re-exporting settings and detection symbols.

## Verification Commands

```bash
venv/bin/python -m compileall app tests run.py
venv/bin/python scripts/run_fast_tests.py
venv/bin/python scripts/run_heavy_tests.py
venv/bin/python scripts/evaluate_benchmark.py benchmark_sets/realworld_v2_150 --output-dir /tmp/realworld_eval
```

The fast/heavy test entrypoints disable repo-local `.env.local` overrides so unit
and benchmark runs stay hermetic across developer machines.

## When Changing the System

- If you are changing detection behavior, start with `app/pii_catalog.py` and `app/pii_match_filters.py`.
- If you are changing extraction behavior, start with `app/processing/attachment_handler.py`, `app/models.py`, and the relevant extractor.
- If you are changing ownership logic, start with `app/processing/entity_resolution_attribution.py`.
- If you are changing AI-assisted review behavior, start with `app/processing/entity_resolution_llm.py` and `app/processing/local_llm_file_qa.py`.
- If you are changing benchmark or product-quality scoring, start with `app/benchmarking/evaluator.py`.
- If you are changing reviewer-facing output, start with `app/reporting/*` and `app/static/index.html`.

## Current Strategy Notes

- Born-digital documents and OCR-derived documents are treated as different extraction modes.
- PDF extraction now prefers layout-aware digital text and table extraction, then OCRs only thin-text pages.
- Image/PDF OCR preserves line structure and captures confidence so QA can escalate uncertain extractions.
- File-level AI QA is intentionally selective. It is not the primary detector and should only run on uncertain, structured, or high-risk files.
