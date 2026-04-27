"""Runtime setup diagnostics and local-LLM onboarding helpers."""

from __future__ import annotations

from dataclasses import asdict
from threading import RLock, Thread
from typing import Any, Optional
import subprocess
import sys

from app.processing.local_llm_attribution import LocalLLMAttributionHelper
from app.processing.local_llm_common import StructuredObjectParser, request_json
from app.runtime_metadata import get_runtime_metadata
from app.settings import (
    LOCAL_LLM_BASE_URL,
    LOCAL_LLM_ENABLED,
    LOCAL_LLM_FILE_QA_ENABLED,
    LOCAL_LLM_MODEL,
    LOCAL_LLM_PROVIDER,
    LOCAL_LLM_TIMEOUT_SECONDS,
    OCR_LANGUAGES,
)
from app.setup_runtime_modules.models import (
    DEPENDENCY_OCR,
    DEPENDENCY_OLLAMA,
    SetupCheck,
    SetupTaskState,
    StructuredCheckState,
    utc_now,
)
from app.setup_runtime_modules.platform import command_status, resolve_install_spec, upload_dir_status
from app.setup_runtime_modules.ui import build_ui_contract

_command_status = command_status
_resolve_install_spec = resolve_install_spec
_upload_dir_status = upload_dir_status


class SetupRuntimeCoordinator:
    """Own setup diagnostics and background local-model bootstrap actions."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._task_state = SetupTaskState()
        self._structured_check_state: Optional[StructuredCheckState] = None

    def get_status(self, *, deep: bool = False) -> dict[str, Any]:
        runtime_metadata = get_runtime_metadata()
        checks = self._collect_checks(deep=deep)
        structured_validation_completed = self._structured_check_completed()
        recommended_actions = self._recommended_actions(checks)
        structured_ready = checks["structured_generation"].ok if (deep or structured_validation_completed) else True
        wizard_ready = (
            checks["upload_dir"].ok
            and checks["tesseract"].ok
            and checks["ollama_cli"].ok
            and checks["ollama_service"].ok
            and checks["model_installed"].ok
            and checks["integration"].ok
            and structured_ready
        )
        with self._lock:
            task_state = self._task_state.to_dict()
        ui = build_ui_contract(
            checks=checks,
            task_state=task_state,
            wizard_ready=wizard_ready,
            deep=deep,
            structured_validation_completed=structured_validation_completed,
            recommended_actions=recommended_actions,
            resolve_install_spec=_resolve_install_spec,
        )

        return {
            "build": runtime_metadata,
            "configured": {
                "local_llm_enabled": LOCAL_LLM_ENABLED,
                "file_qa_enabled": LOCAL_LLM_FILE_QA_ENABLED,
                "provider": LOCAL_LLM_PROVIDER,
                "model": LOCAL_LLM_MODEL,
                "base_url": LOCAL_LLM_BASE_URL,
                "ocr_languages": OCR_LANGUAGES,
                "python": sys.version.split()[0],
            },
            "checks": {key: asdict(value) for key, value in checks.items()},
            "task": task_state,
            "pull": task_state,
            "wizard_ready": wizard_ready,
            "recommended_actions": recommended_actions,
            "system_check_depth": "deep" if deep else "basic",
            "ui": ui,
        }

    def prime_structured_generation_check(self) -> None:
        checks = self._collect_checks(deep=False)
        prerequisites_ready = self._prerequisites_ready(checks)
        if not prerequisites_ready:
            self._invalidate_structured_check()
            return
        if self._structured_check_completed():
            return
        structured_ok, structured_detail = self._structured_generation_status()
        with self._lock:
            self._structured_check_state = StructuredCheckState(
                ok=structured_ok,
                detail=structured_detail,
                checked_at=utc_now(),
            )

    def start_ollama_service(self) -> tuple[bool, dict[str, Any]]:
        self._invalidate_structured_check()
        cli_ok, cli_detail = _command_status(["ollama", "--version"])
        if not cli_ok:
            return False, {"message": cli_detail}

        service_ok, service_detail, _ = self._ollama_service_status()
        if service_ok:
            return True, {"message": service_detail}

        try:
            subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )
        except Exception as exc:
            return False, {"message": f"Failed to start Ollama: {exc}"}

        return True, {"message": "Started `ollama serve` in the background. Run system check again in a few seconds."}

    def start_model_pull(self) -> tuple[bool, dict[str, Any]]:
        self._invalidate_structured_check()
        with self._lock:
            if self._task_state.status == "running":
                return False, {
                    "message": "A background setup task is already in progress.",
                    "task": self._task_state.to_dict(),
                }

        cli_ok, cli_detail = _command_status(["ollama", "--version"])
        if not cli_ok:
            return False, {"message": cli_detail}

        service_ok, service_detail, tags_payload = self._ollama_service_status()
        if not service_ok:
            return False, {"message": service_detail}

        model_names = {model.get("name", "") for model in tags_payload.get("models", [])}
        if LOCAL_LLM_MODEL in model_names:
            return True, {
                "message": f"Model `{LOCAL_LLM_MODEL}` is already installed.",
                "task": self._snapshot_task_state(status="succeeded", detail="Model already installed."),
            }

        thread = Thread(target=self._run_model_pull, daemon=True)
        with self._lock:
            self._task_state = SetupTaskState(
                status="running",
                kind="model_pull",
                subject=LOCAL_LLM_MODEL,
                detail=f"Pulling `{LOCAL_LLM_MODEL}` with Ollama.",
                started_at=utc_now(),
            )
            self._task_state.log_tail.append(f"ollama pull {LOCAL_LLM_MODEL}")
        thread.start()
        return True, {
            "message": f"Started pulling `{LOCAL_LLM_MODEL}`.",
            "task": self._snapshot_task_state(),
        }

    def start_dependency_install(self, dependency: str) -> tuple[bool, dict[str, Any]]:
        self._invalidate_structured_check()
        with self._lock:
            if self._task_state.status == "running":
                return False, {
                    "message": "A background setup task is already in progress.",
                    "task": self._task_state.to_dict(),
                }

        install_spec = _resolve_install_spec(dependency)
        if install_spec is None:
            return False, {"message": "Automatic install is not supported for that dependency on this machine."}

        if dependency == DEPENDENCY_OLLAMA:
            cli_ok, cli_detail = _command_status(["ollama", "--version"])
            if cli_ok:
                return True, {
                    "message": cli_detail,
                    "task": self._snapshot_task_state(status="succeeded", detail=cli_detail),
                }
        elif dependency == DEPENDENCY_OCR:
            ocr_ok, ocr_detail = _command_status(["tesseract", "--version"])
            if ocr_ok:
                return True, {
                    "message": ocr_detail,
                    "task": self._snapshot_task_state(status="succeeded", detail=ocr_detail),
                }
        else:
            return False, {"message": "Unsupported dependency install request."}

        thread = Thread(target=self._run_dependency_install, args=(install_spec,), daemon=True)
        with self._lock:
            self._task_state = SetupTaskState(
                status="running",
                kind="dependency_install",
                subject=install_spec.dependency,
                detail=f"Installing {install_spec.label}.",
                started_at=utc_now(),
            )
            self._task_state.log_tail.append(install_spec.display_command)
        thread.start()
        return True, {
            "message": f"Started installing {install_spec.label}.",
            "task": self._snapshot_task_state(),
        }

    def _snapshot_task_state(self, status: Optional[str] = None, detail: Optional[str] = None) -> dict[str, Any]:
        with self._lock:
            if status is not None:
                self._task_state.status = status
            if detail is not None:
                self._task_state.detail = detail
            return self._task_state.to_dict()

    def _run_model_pull(self) -> None:
        try:
            process = subprocess.Popen(
                ["ollama", "pull", LOCAL_LLM_MODEL],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except Exception as exc:
            with self._lock:
                self._task_state.status = "failed"
                self._task_state.detail = f"Failed to start model pull: {exc}"
                self._task_state.completed_at = utc_now()
            return

        assert process.stdout is not None
        for raw_line in process.stdout:
            line = raw_line.strip()
            if not line:
                continue
            with self._lock:
                self._task_state.log_tail.append(line)

        return_code = process.wait()
        with self._lock:
            self._task_state.completed_at = utc_now()
            if return_code == 0:
                self._task_state.status = "succeeded"
                self._task_state.detail = f"Model `{LOCAL_LLM_MODEL}` is installed and ready."
                self._structured_check_state = None
            else:
                self._task_state.status = "failed"
                self._task_state.detail = f"`ollama pull {LOCAL_LLM_MODEL}` exited with code {return_code}."
                self._structured_check_state = None

    def _run_dependency_install(self, install_spec) -> None:
        try:
            process = subprocess.Popen(
                install_spec.command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except Exception as exc:
            with self._lock:
                self._task_state.status = "failed"
                self._task_state.detail = f"Failed to start installation for {install_spec.label}: {exc}"
                self._task_state.completed_at = utc_now()
            return

        assert process.stdout is not None
        for raw_line in process.stdout:
            line = raw_line.strip()
            if not line:
                continue
            with self._lock:
                self._task_state.log_tail.append(line)

        return_code = process.wait()
        with self._lock:
            self._task_state.completed_at = utc_now()
            if return_code == 0:
                self._task_state.status = "succeeded"
                self._task_state.detail = f"{install_spec.label} install completed. Run the startup checks again if the workspace does not unlock automatically."
            else:
                self._task_state.status = "failed"
                self._task_state.detail = f"{install_spec.label} install exited with code {return_code}."
            self._structured_check_state = None

    def _collect_checks(self, *, deep: bool) -> dict[str, SetupCheck]:
        upload_ok, upload_detail = _upload_dir_status()
        tesseract_ok, tesseract_detail = _command_status(["tesseract", "--version"])
        ollama_cli_ok, ollama_cli_detail = _command_status(["ollama", "--version"])
        ollama_service_ok, ollama_service_detail, tags_payload = self._ollama_service_status()
        model_ok = False
        model_detail = "Ollama is not reachable yet."
        if ollama_service_ok:
            model_names = sorted(model.get("name", "") for model in tags_payload.get("models", []) if model.get("name"))
            if LOCAL_LLM_MODEL in model_names:
                model_ok = True
                model_detail = f"Configured model `{LOCAL_LLM_MODEL}` is installed."
            else:
                model_detail = (
                    f"Configured model `{LOCAL_LLM_MODEL}` is missing. "
                    f"Installed models: {', '.join(model_names) if model_names else 'none'}"
                )

        integration_ok = LOCAL_LLM_ENABLED and LOCAL_LLM_PROVIDER == "ollama"
        if integration_ok:
            integration_detail = f"Runtime is configured for {LOCAL_LLM_PROVIDER}/{LOCAL_LLM_MODEL}."
        else:
            integration_detail = (
                "Local AI integration is not enabled in runtime settings. "
                "Set PII_LOCAL_LLM_ENABLED=1 and restart the analyzer."
            )

        structured_ok, structured_detail = self._structured_generation_check(
            deep=deep,
            prerequisites_ready=(
                upload_ok
                and tesseract_ok
                and ollama_cli_ok
                and ollama_service_ok
                and model_ok
                and integration_ok
            ),
        )

        return {
            "upload_dir": SetupCheck("Upload directory", upload_ok, upload_detail),
            "tesseract": SetupCheck("OCR dependency", tesseract_ok, tesseract_detail),
            "ollama_cli": SetupCheck("Ollama CLI", ollama_cli_ok, ollama_cli_detail),
            "ollama_service": SetupCheck("Ollama service", ollama_service_ok, ollama_service_detail),
            "model_installed": SetupCheck("Recommended model", model_ok, model_detail),
            "integration": SetupCheck("App integration", integration_ok, integration_detail),
            "structured_generation": SetupCheck("Structured AI check", structured_ok, structured_detail),
        }

    def _ollama_service_status(self) -> tuple[bool, str, dict[str, Any]]:
        try:
            payload = request_json(LOCAL_LLM_BASE_URL.rstrip("/"), min(LOCAL_LLM_TIMEOUT_SECONDS, 6.0), "/api/tags", method="GET")
        except Exception as exc:
            return False, f"Could not reach Ollama at {LOCAL_LLM_BASE_URL}: {exc}", {}
        return True, f"Ollama is reachable at {LOCAL_LLM_BASE_URL}.", payload

    def _invalidate_structured_check(self) -> None:
        with self._lock:
            self._structured_check_state = None

    def _structured_check_completed(self) -> bool:
        with self._lock:
            return self._structured_check_state is not None

    @staticmethod
    def _prerequisites_ready(checks: dict[str, SetupCheck]) -> bool:
        return (
            checks["upload_dir"].ok
            and checks["tesseract"].ok
            and checks["ollama_cli"].ok
            and checks["ollama_service"].ok
            and checks["model_installed"].ok
            and checks["integration"].ok
        )

    def _structured_generation_check(self, *, deep: bool, prerequisites_ready: bool) -> tuple[bool, str]:
        if not prerequisites_ready:
            self._invalidate_structured_check()
            return False, "Run the system check to validate structured generation."

        if not deep:
            with self._lock:
                cached = self._structured_check_state
            if cached is not None:
                return cached.ok, cached.detail
            return False, "Run the system check to validate structured generation."

        structured_ok, structured_detail = self._structured_generation_status()
        with self._lock:
            self._structured_check_state = StructuredCheckState(
                ok=structured_ok,
                detail=structured_detail,
                checked_at=utc_now(),
            )
        return structured_ok, structured_detail

    def _structured_generation_status(self) -> tuple[bool, str]:
        helper = LocalLLMAttributionHelper(enabled=True)
        ok, message = helper.probe()
        if not ok:
            return False, message
        try:
            response = request_json(
                helper.base_url,
                min(helper.timeout_seconds, 15.0),
                "/api/generate",
                payload={
                    "model": helper.model,
                    "prompt": 'Return only {"ok": true}.',
                    "stream": False,
                    "think": False,
                    "format": {
                        "type": "object",
                        "properties": {"ok": {"type": "boolean"}},
                        "required": ["ok"],
                    },
                    "options": {
                        "temperature": 0,
                        "num_predict": 32,
                    },
                },
                method="POST",
            )
            parsed = StructuredObjectParser.extract_response_object(str(response.get("response", "")))
        except Exception as exc:
            return False, f"Structured generation probe failed: {exc}"

        if isinstance(parsed, dict) and parsed.get("ok") is True:
            return True, "Structured generation probe succeeded."
        return False, "Model responded, but structured generation output did not validate."

    def _recommended_actions(self, checks: dict[str, SetupCheck]) -> list[str]:
        actions: list[str] = []
        if not checks["ollama_cli"].ok:
            if _resolve_install_spec(DEPENDENCY_OLLAMA) is not None:
                actions.append("Install Ollama from the startup wizard, then start the local runtime.")
            else:
                actions.append("Install Ollama from https://ollama.com/download")
        elif not checks["ollama_service"].ok:
            actions.append("Start the local runtime with `ollama serve` or use the in-app start button.")
        elif not checks["model_installed"].ok:
            actions.append(f"Pull the recommended model with `ollama pull {LOCAL_LLM_MODEL}` or use the in-app pull button.")

        if not checks["tesseract"].ok:
            if _resolve_install_spec(DEPENDENCY_OCR) is not None:
                actions.append("Install OCR support from the startup wizard for full scanned-document coverage.")
            else:
                actions.append("Install Tesseract OCR for full scanned-document coverage.")

        if not checks["integration"].ok:
            actions.append("Enable local AI integration in runtime settings and restart the analyzer.")

        if not actions:
            actions.append("System is ready. Run a sample analysis or upload a benchmark batch.")
        return actions


_setup_runtime_coordinator: Optional[SetupRuntimeCoordinator] = None


def get_setup_runtime_coordinator() -> SetupRuntimeCoordinator:
    global _setup_runtime_coordinator
    if _setup_runtime_coordinator is None:
        _setup_runtime_coordinator = SetupRuntimeCoordinator()
    return _setup_runtime_coordinator
