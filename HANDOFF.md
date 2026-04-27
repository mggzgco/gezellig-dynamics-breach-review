# PII Breach Analyzer Handoff

## Current Objective

The system was overhauled to improve:

- PII detection accuracy
- entity-level attribution
- report quality
- UI quality
- downstream review usability

The codebase is **not** a git repository in this environment, so this handoff file is the main state-transfer artifact for continuing the work elsewhere.

## What Changed

### Detection and Schema

- Reworked the PII schema behind a stable `app/config.py` facade
- Split runtime settings into `app/settings.py`
- Split the detection core into focused modules:
  - `app/pii_keywords.py`
  - `app/pii_normalization.py`
  - `app/pii_validation.py`
  - `app/pii_match_filters.py`
  - `app/pii_pattern_types.py`
  - `app/pii_core.py`
- Split the concrete rule registry into domain modules:
  - `app/pii_catalog_government.py`
  - `app/pii_catalog_financial.py`
  - `app/pii_catalog_health.py`
  - `app/pii_catalog_personal.py`
  - aggregated by `app/pii_catalog.py`
- Added category/subtype metadata for findings
- Added stronger validators and better pattern gating
- Added confidence scoring and duplicate suppression in `app/processing/pii_engine.py`
- Fixed major false positives, especially bogus driver's-license matches from ordinary numbers, dates, prices, and counts

### Coverage

- Subject lines are now scanned
- Attachment filenames are now scanned
- Source text is preserved per scan source in `EmailAnalysisResult.source_texts`
- Source extraction metadata is preserved per scan source in `EmailAnalysisResult.source_extractions`
- HTML email extraction was improved
- Spreadsheet, ZIP, and OCR extraction quality was improved
- PDF extraction now uses layout-aware digital text/table extraction plus page-level OCR fallback
- Image OCR now uses local Tesseract TSV parsing so line structure and OCR confidence survive extraction
- Nested `.eml` attachments are now extracted as attachments instead of bleeding into parent body text

### Entity Attribution

- Replaced participant-level fanout attribution with content-first attribution
- Split entity resolution by concern:
  - `app/processing/entity_resolver.py`
  - `app/processing/entity_resolution_models.py`
  - `app/processing/entity_resolution_utils.py`
  - `app/processing/entity_resolution_extraction.py`
  - `app/processing/entity_resolution_attribution.py`
  - `app/processing/entity_resolution_llm.py`
- `app/processing/person_resolver.py` now resolves entities from content blocks rather than assigning every finding to every participant
- Attribution now prefers:
  - labeled names
  - labeled emails
  - inline `Name <email>` anchors
  - tabular rows
  - salutations
  - constrained direct-notice fallback
- If ownership is weak or ambiguous, findings stay `UNATTRIBUTED` instead of being forced onto a person

### Scoring and Reporting

- Risk scoring now uses unique normalized values instead of blindly counting duplicates
- Confidence affects risk contribution
- Attributed identity now counts in risk combinations
- HTML report was redesigned
- Report view-model preparation is separated from HTML template rendering
- CSV export was expanded with attribution metadata
- A dedicated file-level AI QA CSV export is available from the UI and API
- File QA now uses extraction-quality signals, especially low-confidence OCR and structured scanned sources, to block unsafe auto-clears
- File QA is selective by default rather than reviewing every file
- UI was redesigned for a more serious review workflow

### Benchmarking

- Added `app/benchmarking/ground_truth.py`
- Added `app/benchmarking/evaluator.py`
- Split benchmark generation into:
  - `app/benchmarking/fixtures.py`
  - `app/benchmarking/attachments.py`
  - `app/benchmarking/scenarios.py`
  - `app/benchmarking/generator.py`
- Added `scripts/generate_benchmark_dataset.py`
- Added `scripts/evaluate_benchmark.py`
- Added a machine-readable `ground_truth.json` benchmark format
- Added a reproducible 300-file benchmark generator with real parseable attachments
- Added an evaluation harness that reports:
  - finding-level precision/recall
  - report-layer file/type precision/recall
  - owner-aware report precision/recall
  - human-review escalation precision/recall

## Key Files Changed

- `ARCHITECTURE.md`
- `app/settings.py`
- `app/config.py`
- `app/pii_keywords.py`
- `app/pii_normalization.py`
- `app/pii_validation.py`
- `app/pii_match_filters.py`
- `app/pii_pattern_types.py`
- `app/pii_core.py`
- `app/pii_catalog.py`
- `app/pii_catalog_government.py`
- `app/pii_catalog_financial.py`
- `app/pii_catalog_health.py`
- `app/pii_catalog_personal.py`
- `app/models.py`
- `app/processing/pii_engine.py`
- `app/processing/pipeline.py`
- `app/processing/risk_scorer.py`
- `app/processing/eml_parser.py`
- `app/processing/entity_resolver.py`
- `app/processing/entity_resolution_models.py`
- `app/processing/entity_resolution_utils.py`
- `app/processing/entity_resolution_extraction.py`
- `app/processing/entity_resolution_attribution.py`
- `app/processing/entity_resolution_llm.py`
- `app/processing/person_resolver.py`
- `app/processing/extractors/image_extractor.py`
- `app/processing/extractors/ocr_layout.py`
- `app/processing/extractors/pdf_extractor.py`
- `app/processing/extractors/types.py`
- `app/processing/extractors/xlsx_extractor.py`
- `app/processing/extractors/zip_extractor.py`
- `app/benchmarking/ground_truth.py`
- `app/benchmarking/fixtures.py`
- `app/benchmarking/attachments.py`
- `app/benchmarking/scenarios.py`
- `app/benchmarking/generator.py`
- `app/benchmarking/evaluator.py`
- `app/reporting/html_report.py`
- `app/reporting/templates/report.html.j2`
- `app/reporting/csv_report.py`
- `app/api/jobs.py`
- `app/api/reports.py`
- `app/static/index.html`
- `app/reporting/file_review_csv.py`
- `app/processing/local_llm_file_qa.py`
- `tests/test_pii_detection.py`
- `tests/test_entity_attribution.py`
- `tests/test_benchmarking.py`

## Verification Already Run

These pass on the current cleaned build:

```bash
venv/bin/python -m compileall app tests run.py
venv/bin/python scripts/run_fast_tests.py
venv/bin/python scripts/run_heavy_tests.py
venv/bin/python scripts/evaluate_benchmark.py benchmark_sets/realworld_v2_150 --output-dir /tmp/realworld_v2_cleanup_eval7
```

Most recent benchmark result on `benchmark_sets/realworld_v2_150`:

- precision: `1.0`
- recall: `1.0`
- false positives: `0`
- false negatives: `0`

Most recent AI-QA sample audit on a `5`-file `realworld_v2` subset:

- exact finding metrics: `precision 1.0 / recall 1.0`
- owner-aware report metrics: `precision 1.0 / recall 1.0`
- review escalation metrics: `precision 0.5 / recall 1.0`
- AI reviewed files: `3`

Operational note:

- local generation health is good, but full-corpus AI QA throughput is still slower than deterministic scoring
- that is why file-level AI QA is now selective by default rather than all-files-by-default

## Concrete Behavior Improvements Confirmed

- `email_022.eml` no longer produces large volumes of fake `DRIVERS_LICENSE` findings
- `email_113.eml` no longer produces large volumes of fake `DRIVERS_LICENSE` findings
- `email_121.eml` no longer produces large volumes of fake `DRIVERS_LICENSE` findings
- `email_006.eml` now attributes `ADDRESS` and `PHONE` to Sarah Chen
- `email_008.eml` now attributes `BANK_ACCOUNT` and `PHONE` to Anna Weber
- weak-owner attachment cases can remain `UNATTRIBUTED` instead of being misassigned

## Current Architecture Summary

### PII Detection

Primary file:

- `app/processing/pii_engine.py`
- `app/pii_catalog.py`

Current model:

- deterministic pattern-based detection
- validators where possible
- confidence scoring
- exact context matching
- deduplication by normalized value
- domain-specific rule modules aggregated into one ordered public catalog

### Entity Attribution

Primary file:

- `app/processing/entity_resolver.py`
- `app/processing/entity_resolution_attribution.py`
- `app/processing/entity_resolution_llm.py`
- `app/processing/local_llm_attribution.py`

Current model:

- split source text into blocks
- extract entity anchors per block
- attribute each finding to the best-supported entity
- use neighboring block support where justified
- only use header fallback in constrained cases
- otherwise leave unattributed
- optionally route ambiguous blocks to a local LLM
- local LLM attribution is gated, JSON-validated, evidence-validated, and capped per email
- deterministic logic remains the source of truth if the model is unavailable or weak
- owner-aware benchmark scoring now measures this layer separately from raw detection

### Reports / UI

Primary files:

- `app/reporting/html_report.py`
- `app/reporting/templates/report.html.j2`
- `app/reporting/csv_report.py`
- `app/static/index.html`

Current model:

- confidence-aware review output
- attribution metadata exposed to reviewers
- improved executive summary and per-record detail
- build/schema metadata stamped into exported artifacts
- file-level AI QA can trigger a bounded deterministic follow-up scan for suspected missing types before attribution

### Developer Orientation

Start with:

- `ARCHITECTURE.md`
- `app/settings.py`
- `app/config.py`
- `app/pii_catalog.py`
- `app/processing/pipeline.py`

## Known Limitations

The system is significantly stronger than the original, but it is **not** the ceiling.

Remaining limitations:

- attribution is still primarily deterministic and heuristic
- document layout understanding is limited
- OCR-heavy documents remain imperfect
- merged-cell spreadsheets and complex tables are not fully modeled
- multi-person narratives with pronouns or long-range references remain hard
- the benchmark is now machine-readable and reproducible, but it is still synthetic rather than harvested from de-identified real incidents
- the local LLM path currently targets Ollama-style runtimes and candidate arbitration, not free-form entity extraction

## Best Next Step

Highest-value next phase:

1. Expand the benchmark with de-identified real-world layouts and harder OCR/table samples
2. Create a labeled corpus with:
   - finding truth
   - owner truth
   - unattributed truth
3. Measure the hybrid deterministic + local-LLM attribution path against that corpus
4. Keep deterministic detection as the primary source of truth for raw PII detection

Recommended implementation shape for local-model support:

- deterministic scan first
- deterministic entity-anchor extraction first
- route only ambiguous blocks/findings to a local model
- require strict JSON output
- require evidence spans
- reject weak outputs and fall back to `UNATTRIBUTED`

## Suggested Next Development Tasks

In recommended order:

1. Create an attribution eval dataset and scoring harness
2. Improve table/form/layout extraction for PDFs and spreadsheets
3. Add relationship modeling for dependent/spouse/child cases
4. Add per-finding attribution audit views in the HTML report
5. Expand the local LLM path beyond candidate arbitration only after eval coverage exists

## Quick Resume Commands

From the project root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
.venv/bin/python -m compileall app tests run.py
.venv/bin/python scripts/run_fast_tests.py
.venv/bin/python scripts/run_heavy_tests.py
.venv/bin/python scripts/evaluate_benchmark.py benchmark_sets/realworld_v2_150 --output-dir /tmp/realworld_v2_resume_eval
python run.py
```

Optional local LLM runtime:

```bash
ollama serve
ollama pull qwen3:4b
.venv/bin/python scripts/check_local_llm.py
```

Notes:

- this checkout now auto-loads `.env.local`
- `.env.local` currently enables the local Ollama + `qwen3:4b` hybrid path by default
- explicit shell environment variables still override `.env.local`

If you want to regenerate a quick verification report programmatically, use the current pipeline and reporting modules against sample files in:

- `jobs/5bcb3736-67b0-4e76-8477-4dd5638f4589/uploads`

## Notes For A New Environment

- Bring the full project directory, not just this file
- Do not rely on a bundled `venv/` from another machine or OS; create a fresh local `.venv`
- Reinstall from `requirements.txt` in the target environment before resuming
- This handoff assumes the codebase already contains all changes listed above
- If work resumes in a git-backed environment, initialize git immediately and commit the current state before continuing
