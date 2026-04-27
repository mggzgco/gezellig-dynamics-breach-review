# Customer Setup Guide

Use this guide if you are a customer or analyst setting up **Gezellig Dynamics Breach Review** on your own machine for the first time.

This product runs **locally** on your computer and opens in your browser at:

```text
http://127.0.0.1:8000
```

It is not a hosted SaaS product.

## What you need before you start

- A local copy of this repository
- Python 3 installed on the machine
- Permission to install local tools if Ollama or OCR support is missing

## Fastest setup path

### macOS

Open Terminal in the repository folder and run:

```bash
./scripts/bootstrap_macos.sh
```

### Windows PowerShell

Open PowerShell in the repository folder and run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\bootstrap_windows.ps1
```

Those scripts:

- create a fresh `.venv`
- install Python dependencies
- start the app locally

Then open:

```text
http://127.0.0.1:8000
```

## What happens after the app opens

The app checks the local system automatically.

It verifies:

- upload directory access
- OCR support (`tesseract`)
- Ollama CLI
- Ollama local service
- recommended model `qwen3:4b`
- final structured local-AI validation

If something is missing:

- the review workspace stays locked
- the startup wizard opens automatically
- the top banner shows the current readiness state

## Local LLM setup

The product expects:

- provider: `ollama`
- model: `qwen3:4b`

If Ollama is missing, the wizard will do the most automatic thing the machine supports:

- on macOS with Homebrew: start the install from the UI
- on Windows with `winget` or `choco`: start the install from the UI
- otherwise: show the correct download/install guidance

If Ollama is installed but not running, the wizard can:

- start `ollama serve`

If Ollama is running but the model is missing, the wizard can:

- pull `qwen3:4b`

When setup completes successfully, the workspace unlocks automatically.

## If you see this, do this

### “Install Ollama to continue”

Do this:

- use the wizard’s `Install Ollama` action if available
- otherwise install from:
  - `https://ollama.com/download`

Then reopen the app or rerun the startup checks.

### “Start Ollama to finish setup”

Do this:

- click `Start Ollama` in the wizard
- or run manually:

```bash
ollama serve
```

Leave it running, then rerun the startup check.

### “Download qwen3:4b to continue”

Do this:

- click `Pull qwen3:4b` in the wizard
- or run manually:

```bash
ollama pull qwen3:4b
```

### “Install OCR support to continue”

OCR support is needed for scanned PDFs and image-based evidence.

On macOS with Homebrew:

```bash
brew install tesseract libmagic
```

On Windows:

- install Tesseract OCR
- ensure `tesseract.exe` is on your `PATH`

Then rerun the startup checks.

### “Check local AI integration”

This means Ollama and the model exist, but the structured validation did not pass.

Do this:

1. make sure Ollama is still running
2. rerun the full startup check in the wizard
3. if needed, verify manually:

```bash
.venv/bin/python scripts/check_local_llm.py
```

On Windows PowerShell:

```powershell
.venv\Scripts\python.exe .\scripts\check_local_llm.py
```

## First use

Once the workspace unlocks:

1. open `Review workspace`
2. upload only `.eml` files
3. run the analysis
4. review:
   - HTML report
   - analyst CSV
   - file-review / AI-QA CSV
5. use `Saved runs` to reopen or delete prior runs

## Important notes

- The app binds to `127.0.0.1` only
- Do not expose it directly to untrusted networks
- Uploaded jobs and results are stored locally in the `jobs/` directory

## If you need more detail

See:

- [README.md](README.md)
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
