# Gezellig Dynamics Breach Review

Local breach-review workspace for `.eml` evidence batches. The app ingests exported email evidence, extracts attachments and scans, detects exposed personal data, resolves likely owners, and produces HTML / CSV analyst outputs.

This repository is ready for a controlled customer beta or technical handoff. The product is designed to run locally on the analyst's machine and guide the rest of the Ollama/model setup from inside the UI after the app starts.

## What the product does

- Ingests exported `.eml` batches
- Extracts nested attachments including `PDF`, `DOCX`, `XLSX`, `ZIP`, `MSG`, `RTF`, images, and nested `.eml`
- Runs OCR on scanned evidence
- Produces:
  - HTML review report
  - analyst CSV
  - file-review / AI-QA CSV
- Persists review runs so they can be reopened or deleted in the UI

## What the product does not do

- It does not install Python for the user
- It does not guarantee unattended system installs on every machine
- It is intended for local use on `127.0.0.1`, not public internet exposure

## Quick start

### macOS

```bash
./scripts/bootstrap_macos.sh
```

### Windows PowerShell

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\bootstrap_windows.ps1
```

Both scripts:

- create a local virtual environment in `.venv`
- install Python dependencies
- start the app on `http://127.0.0.1:8000`

If OCR or Ollama are missing, the product's startup wizard will guide the rest of the setup.

## Manual start

### 1. Create a virtual environment

macOS / Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows PowerShell:

```powershell
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Start the app

```bash
python run.py
```

Then open:

```text
http://127.0.0.1:8000
```

## Startup wizard

On load, the app now:

1. Runs startup checks automatically
2. Validates:
   - upload directory
   - Tesseract OCR
   - Ollama CLI
   - Ollama service
   - recommended model `qwen3:4b`
   - structured-generation readiness
3. Locks the review workspace until readiness is confirmed
4. Opens the startup wizard automatically if anything is missing

When supported by the local machine, the startup wizard can:

- install Ollama from the UI using `brew`, `winget`, or `choco`
- install OCR support from the UI using `brew`, `winget`, or `choco`
- start `ollama serve`
- pull `qwen3:4b`
- rerun the full system validation

## Environment configuration

Use `.env.local` for local overrides. A safe starter file is provided:

```text
.env.example
```

Copy it to `.env.local` and adjust only if you need non-default behavior.

## Default local AI settings

- Provider: `ollama`
- Model: `qwen3:4b`
- Base URL: `http://127.0.0.1:11434`

## Tests

Fast suite:

```bash
venv/bin/python scripts/run_fast_tests.py
```

Heavy benchmark-generation suite:

```bash
venv/bin/python scripts/run_heavy_tests.py
```

## Repository contents

- `app/`: application code
- `scripts/`: bootstrap, verification, and benchmark utilities
- `tests/`: fast and heavy test suites
- `benchmark_sets/`: synthetic benchmark corpora
- `ARCHITECTURE.md`: technical structure overview
- `HANDOFF.md`: implementation/handoff notes

## Shipping note

This repository is ready to push to a new GitHub repo for technical customer delivery. It is not yet packaged as a signed macOS or Windows installer.
