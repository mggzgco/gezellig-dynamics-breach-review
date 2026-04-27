"""Platform-specific checks and install spec resolution for setup runtime."""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys

from app.settings import UPLOAD_DIR

from .models import DEPENDENCY_OCR, DEPENDENCY_OLLAMA, InstallSpec


def command_status(command: list[str], *, timeout: float = 6.0) -> tuple[bool, str]:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        return False, f"{command[0]} is not installed."
    except Exception as exc:
        return False, f"{command[0]} check failed: {exc}"

    output = (completed.stdout or completed.stderr or "").strip().splitlines()
    detail = output[0].strip() if output else f"{command[0]} returned code {completed.returncode}"
    return completed.returncode == 0, detail


def upload_dir_status() -> tuple[bool, str]:
    try:
        upload_dir = Path(UPLOAD_DIR)
        upload_dir.mkdir(parents=True, exist_ok=True)
        probe_file = upload_dir / ".write_probe"
        probe_file.write_text("ok", encoding="utf-8")
        probe_file.unlink(missing_ok=True)
        return True, f"Upload directory is writable at {upload_dir.resolve()}"
    except Exception as exc:
        return False, f"Upload directory is not writable: {exc}"


def resolve_install_spec(dependency: str) -> InstallSpec | None:
    if dependency == DEPENDENCY_OLLAMA:
        if sys.platform == "darwin" and shutil.which("brew"):
            return InstallSpec(
                dependency=dependency,
                label="Ollama",
                command=["brew", "install", "ollama"],
                display_command="brew install ollama",
            )
        if sys.platform.startswith("win") and shutil.which("winget"):
            return InstallSpec(
                dependency=dependency,
                label="Ollama",
                command=[
                    "winget",
                    "install",
                    "--id",
                    "Ollama.Ollama",
                    "-e",
                    "--accept-source-agreements",
                    "--accept-package-agreements",
                ],
                display_command="winget install --id Ollama.Ollama -e --accept-source-agreements --accept-package-agreements",
            )
        if sys.platform.startswith("win") and shutil.which("choco"):
            return InstallSpec(
                dependency=dependency,
                label="Ollama",
                command=["choco", "install", "ollama", "-y"],
                display_command="choco install ollama -y",
            )
        return None

    if dependency == DEPENDENCY_OCR:
        if sys.platform == "darwin" and shutil.which("brew"):
            return InstallSpec(
                dependency=dependency,
                label="OCR support",
                command=["brew", "install", "tesseract", "libmagic"],
                display_command="brew install tesseract libmagic",
            )
        if sys.platform.startswith("win") and shutil.which("winget"):
            return InstallSpec(
                dependency=dependency,
                label="OCR support",
                command=[
                    "winget",
                    "install",
                    "--id",
                    "UB-Mannheim.TesseractOCR",
                    "-e",
                    "--accept-source-agreements",
                    "--accept-package-agreements",
                ],
                display_command="winget install --id UB-Mannheim.TesseractOCR -e --accept-source-agreements --accept-package-agreements",
            )
        if sys.platform.startswith("win") and shutil.which("choco"):
            return InstallSpec(
                dependency=dependency,
                label="OCR support",
                command=["choco", "install", "tesseract", "-y"],
                display_command="choco install tesseract -y",
            )
        return None

    return None
