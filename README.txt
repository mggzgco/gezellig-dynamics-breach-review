================================================================================
               GEZELLIG DYNAMICS BREACH REVIEW - START HERE
================================================================================

This repository is prepared for push to a new GitHub repository and for
technical customer handoff.

What the user still needs on the machine before the app can fully work:

- Python 3
- permission to install local tools if Ollama or OCR are missing

What the app does after it starts:

- runs startup checks automatically
- locks the review workspace until the machine is ready
- opens a startup wizard automatically if something is missing
- can install Ollama / OCR from the UI on supported machines
- can start Ollama, pull `qwen3:4b`, and validate the integration


================================================================================
                              FASTEST WAY TO RUN
================================================================================

macOS:

```bash
./scripts/bootstrap_macos.sh
```

Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\bootstrap_windows.ps1
```

Then open:

```text
http://127.0.0.1:8000
```


================================================================================
                              MANUAL WAY TO RUN
================================================================================

1. Create a local virtual environment

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

2. Install Python dependencies

```bash
pip install -r requirements.txt
```

3. Start the app

```bash
python run.py
```


================================================================================
                              STARTUP WIZARD
================================================================================

On first load, the app checks:

- upload directory
- Tesseract OCR
- Ollama CLI
- Ollama service
- recommended model `qwen3:4b`
- structured-generation readiness

If something is missing, the workspace stays locked and the wizard guides the
rest of setup.


================================================================================
                         LOCAL AI DEFAULT CONFIGURATION
================================================================================

- Provider: `ollama`
- Model: `qwen3:4b`
- Base URL: `http://127.0.0.1:11434`

Use `.env.example` as the safe starting point if local overrides are needed.


================================================================================
                           IMPORTANT SHIPPING NOTE
================================================================================

This is a local analyst tool intended to bind to:

```text
127.0.0.1
```

Do not expose it directly to untrusted networks.
