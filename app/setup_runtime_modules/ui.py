"""UI contract builders for the startup wizard and workspace gate."""

from __future__ import annotations

from typing import Any, Callable

from app.settings import LOCAL_LLM_MODEL

from .models import (
    DEPENDENCY_OCR,
    DEPENDENCY_OLLAMA,
    OLLAMA_DOWNLOAD_URL_PLACEHOLDER,
    OLLAMA_INSTALL_COMMAND_PLACEHOLDER,
    TESSERACT_INSTALL_COMMAND_PLACEHOLDER,
    SetupCheck,
)


ResolveInstallSpec = Callable[[str], object | None]


def build_ui_contract(
    *,
    checks: dict[str, SetupCheck],
    task_state: dict[str, Any],
    wizard_ready: bool,
    deep: bool,
    structured_validation_completed: bool,
    recommended_actions: list[str],
    resolve_install_spec: ResolveInstallSpec,
) -> dict[str, Any]:
    state = determine_ui_state(
        checks=checks,
        task_state=task_state,
        deep=deep,
        wizard_ready=wizard_ready,
        structured_validation_completed=structured_validation_completed,
    )
    spec = ui_state_spec(state, resolve_install_spec=resolve_install_spec)
    return {
        "state": state,
        "banner": {
            "level": spec["banner_level"],
            "label": spec["banner_label"],
        },
        "wizard_should_open": not wizard_ready,
        "wizard_summary": (
            "Your local runtime, OCR support, and configured model are ready. You can enter the review workspace."
            if wizard_ready
            else spec["wizard_summary"]
        ),
        "workspace_locked": not wizard_ready,
        "workspace_gate": {
            "title": spec["gate_title"],
            "detail": spec["gate_detail"],
            "actions": spec["gate_actions"],
        },
        "wizard_steps": build_wizard_steps(checks, resolve_install_spec=resolve_install_spec),
        "wizard_primary_actions": (
            [action("Enter product", "continue", style="primary")]
            if wizard_ready
            else spec["wizard_primary_actions"]
        ),
        "recommended_actions": recommended_actions,
        "auto_deep_check_eligible": state == "needs_validation",
    }


def determine_ui_state(
    *,
    checks: dict[str, SetupCheck],
    task_state: dict[str, Any],
    deep: bool,
    wizard_ready: bool,
    structured_validation_completed: bool,
) -> str:
    if wizard_ready:
        return "ready"
    if task_state.get("status") == "running":
        return "setup_task_running"
    if not checks["ollama_cli"].ok:
        return "install_ollama"
    if not checks["ollama_service"].ok:
        return "start_ollama"
    if not checks["model_installed"].ok:
        return "download_model"
    if not checks["tesseract"].ok:
        return "install_ocr"
    if not checks["integration"].ok:
        return "enable_integration"
    if not checks["structured_generation"].ok:
        return "validation_failed" if deep or structured_validation_completed else "needs_validation"
    return "setup_required"


def ui_state_spec(state: str, *, resolve_install_spec: ResolveInstallSpec) -> dict[str, Any]:
    ollama_supported = resolve_install_spec(DEPENDENCY_OLLAMA)
    ocr_supported = resolve_install_spec(DEPENDENCY_OCR)
    ollama_install_actions = dependency_actions(
        DEPENDENCY_OLLAMA,
        include_download=True,
        include_recheck=True,
        resolve_install_spec=resolve_install_spec,
    )
    ocr_install_actions = dependency_actions(
        DEPENDENCY_OCR,
        include_download=False,
        include_recheck=True,
        resolve_install_spec=resolve_install_spec,
    )
    specs = {
        "ready": {
            "banner_level": "ok",
            "banner_label": "System ready",
            "wizard_summary": "The local runtime, OCR support, and recommended model are ready.",
            "gate_title": "System ready",
            "gate_detail": "The workspace is available.",
            "gate_actions": [],
            "wizard_primary_actions": [action("Enter product", "continue", style="primary")],
        },
        "setup_task_running": {
            "banner_level": "warn",
            "banner_label": "Running background setup",
            "wizard_summary": "A background setup task is running now. Keep this window open and the wizard will update automatically.",
            "gate_title": "Background setup is still running",
            "gate_detail": "The workspace will unlock automatically when the task finishes and validation passes.",
            "gate_actions": [action("Open startup wizard", "continue-to-wizard")],
            "wizard_primary_actions": [action("Open startup wizard", "continue-to-wizard", style="secondary")],
        },
        "install_ollama": {
            "banner_level": "error",
            "banner_label": "Install Ollama to continue",
            "wizard_summary": (
                "Ollama is not installed on this machine yet. Install it from the wizard, then rerun the startup checks."
                if ollama_supported
                else "Ollama is not installed on this machine yet. Install it first, then rerun the startup checks."
            ),
            "gate_title": "Install Ollama before using the workspace",
            "gate_detail": "This machine does not have the required local runtime yet.",
            "gate_actions": ollama_install_actions + [action("Open startup wizard", "continue-to-wizard")],
            "wizard_primary_actions": ollama_install_actions[:2],
        },
        "start_ollama": {
            "banner_level": "warn",
            "banner_label": "Start Ollama to finish setup",
            "wizard_summary": "Ollama is installed but not currently running. Start it and the product will recheck automatically.",
            "gate_title": "Start the local runtime",
            "gate_detail": "Ollama is installed, but the service is not yet reachable on localhost.",
            "gate_actions": [
                action("Start Ollama", "start-ollama", style="primary"),
                action("Open startup wizard", "continue-to-wizard"),
            ],
            "wizard_primary_actions": [
                action("Start Ollama", "start-ollama", style="primary"),
                action("Run full check again", "refresh", value="deep"),
            ],
        },
        "download_model": {
            "banner_level": "warn",
            "banner_label": "Download qwen3:4b to continue",
            "wizard_summary": "The local runtime is available, but the recommended qwen3:4b model is not installed yet.",
            "gate_title": "Download the recommended local model",
            "gate_detail": "The review workspace stays locked until the configured model is installed and validated.",
            "gate_actions": [
                action("Pull qwen3:4b", "pull-model", style="primary"),
                action("Open startup wizard", "continue-to-wizard"),
            ],
            "wizard_primary_actions": [
                action("Pull qwen3:4b", "pull-model", style="primary"),
                action("Run full check again", "refresh", value="deep"),
            ],
        },
        "install_ocr": {
            "banner_level": "warn",
            "banner_label": "Install OCR support to continue",
            "wizard_summary": (
                "OCR support is missing. Install it from the wizard before using the workspace so scanned attachments can be processed properly."
                if ocr_supported
                else "OCR support is missing. Install it before using the workspace so scanned attachments can be processed properly."
            ),
            "gate_title": "Install OCR support before starting a review",
            "gate_detail": "Scanned and image-heavy evidence will not be handled correctly until OCR support is installed.",
            "gate_actions": ocr_install_actions + [action("Open startup wizard", "continue-to-wizard")],
            "wizard_primary_actions": ocr_install_actions[:2],
        },
        "enable_integration": {
            "banner_level": "error",
            "banner_label": "Enable local AI integration",
            "wizard_summary": "Local AI integration is disabled in runtime settings. Enable it and restart the analyzer before using the workspace.",
            "gate_title": "Enable local AI integration",
            "gate_detail": "The current runtime configuration does not allow the local model integration the product expects.",
            "gate_actions": [
                action("Open startup wizard", "continue-to-wizard", style="primary"),
                action("Run full check again", "refresh", value="deep"),
            ],
            "wizard_primary_actions": [
                action("Run full check again", "refresh", value="deep", style="primary"),
            ],
        },
        "needs_validation": {
            "banner_level": "warn",
            "banner_label": "Running startup checks",
            "wizard_summary": "Local prerequisites are present. The product is validating the final AI integration automatically.",
            "gate_title": "Validating system readiness",
            "gate_detail": "The workspace will unlock automatically once the final startup checks finish successfully.",
            "gate_actions": [action("Open startup wizard", "continue-to-wizard")],
            "wizard_primary_actions": [action("Run full check again", "refresh", value="deep")],
        },
        "validation_failed": {
            "banner_level": "warn",
            "banner_label": "Check local AI integration",
            "wizard_summary": "The final startup validation did not pass. Review the step details and rerun the checks.",
            "gate_title": "Finish system validation",
            "gate_detail": "The local runtime is present, but the final structured-generation validation did not complete successfully.",
            "gate_actions": [
                action("Run full check again", "refresh", value="deep", style="primary"),
                action("Open startup wizard", "continue-to-wizard"),
            ],
            "wizard_primary_actions": [action("Run full check again", "refresh", value="deep", style="primary")],
        },
        "setup_required": {
            "banner_level": "error",
            "banner_label": "Setup required",
            "wizard_summary": "The workspace is locked until the required local setup is complete.",
            "gate_title": "Finish setup before starting a review",
            "gate_detail": "Use the startup wizard to resolve the remaining requirements.",
            "gate_actions": [action("Open startup wizard", "continue-to-wizard", style="primary")],
            "wizard_primary_actions": [action("Open startup wizard", "continue-to-wizard", style="primary")],
        },
    }
    return specs[state]


def build_wizard_steps(
    checks: dict[str, SetupCheck],
    *,
    resolve_install_spec: ResolveInstallSpec,
) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    if not checks["ollama_cli"].ok:
        install_actions, extras = step_install_actions(
            DEPENDENCY_OLLAMA,
            include_download=True,
            resolve_install_spec=resolve_install_spec,
        )
        steps.append(
            step(
                "install-ollama",
                "Install Ollama",
                "The local runtime is required before the recommended model can be downloaded or validated.",
                "error",
                actions=install_actions,
                extras=extras,
            )
        )
    elif not checks["ollama_service"].ok:
        steps.append(
            step(
                "start-ollama",
                "Start the local runtime",
                checks["ollama_service"].detail or "Ollama is installed but not yet reachable on localhost.",
                "warn",
                actions=[
                    action("Start Ollama", "start-ollama", style="primary"),
                    action("Run full check", "refresh", value="deep"),
                ],
            )
        )
    else:
        steps.append(step("ollama-ready", "Local runtime is reachable", checks["ollama_service"].detail, "ok"))

    if checks["ollama_service"].ok and not checks["model_installed"].ok:
        steps.append(
            step(
                "pull-model",
                "Download the recommended model",
                checks["model_installed"].detail or "The configured qwen3:4b model is not installed yet.",
                "warn",
                actions=[
                    action("Pull qwen3:4b", "pull-model", style="primary"),
                    action("Run full check", "refresh", value="deep"),
                ],
                extras=[f"ollama pull {LOCAL_LLM_MODEL}"],
            )
        )
    elif checks["model_installed"].ok:
        steps.append(step("model-ready", "Recommended model is installed", checks["model_installed"].detail, "ok"))

    if not checks["tesseract"].ok:
        install_actions, extras = step_install_actions(
            DEPENDENCY_OCR,
            include_download=False,
            resolve_install_spec=resolve_install_spec,
        )
        steps.append(
            step(
                "install-ocr",
                "Install OCR support",
                "OCR support is required for scanned attachments and screenshots.",
                "warn",
                actions=install_actions,
                extras=extras,
            )
        )
    else:
        steps.append(step("ocr-ready", "OCR support is available", checks["tesseract"].detail, "ok"))

    if not checks["structured_generation"].ok:
        steps.append(
            step(
                "integration-check",
                "Validate the final integration",
                checks["structured_generation"].detail or "Run the full system check to validate local AI integration.",
                "warn",
                actions=[action("Run full check", "refresh", value="deep", style="primary")],
            )
        )
    else:
        steps.append(
            step(
                "integration-ready",
                "System validation passed",
                checks["structured_generation"].detail,
                "ok",
            )
        )

    return steps


def dependency_actions(
    dependency: str,
    *,
    include_download: bool,
    include_recheck: bool,
    resolve_install_spec: ResolveInstallSpec,
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    install_spec = resolve_install_spec(dependency)
    if install_spec is not None:
        actions.append(
            action(
                f"Install {install_spec.label}",
                "install-dependency",
                value=dependency,
                style="primary",
            )
        )
        actions.append(action("Copy terminal command", "copy", value=install_spec.display_command, style="tertiary"))
    else:
        if dependency == DEPENDENCY_OLLAMA:
            actions.append(action("Open Ollama download", "external", value=OLLAMA_DOWNLOAD_URL_PLACEHOLDER, style="primary"))
            actions.append(action("Copy install guidance", "copy", value=OLLAMA_INSTALL_COMMAND_PLACEHOLDER, style="tertiary"))
        elif dependency == DEPENDENCY_OCR:
            actions.append(action("Copy OCR install guidance", "copy", value=TESSERACT_INSTALL_COMMAND_PLACEHOLDER, style="tertiary"))

    if include_download and dependency == DEPENDENCY_OLLAMA and install_spec is not None:
        actions.append(action("Open Ollama download", "external", value=OLLAMA_DOWNLOAD_URL_PLACEHOLDER))
    if include_recheck:
        actions.append(action("Recheck", "refresh", value="basic"))
    return actions


def step_install_actions(
    dependency: str,
    *,
    include_download: bool,
    resolve_install_spec: ResolveInstallSpec,
) -> tuple[list[dict[str, Any]], list[str]]:
    install_spec = resolve_install_spec(dependency)
    extras: list[str] = []
    if install_spec is not None:
        extras.append(install_spec.display_command)
    elif dependency == DEPENDENCY_OLLAMA:
        extras.append(OLLAMA_INSTALL_COMMAND_PLACEHOLDER)
    elif dependency == DEPENDENCY_OCR:
        extras.append(TESSERACT_INSTALL_COMMAND_PLACEHOLDER)
    return dependency_actions(
        dependency,
        include_download=include_download,
        include_recheck=True,
        resolve_install_spec=resolve_install_spec,
    ), extras


def action(label: str, action_type: str, *, value: str | None = None, style: str = "secondary") -> dict[str, Any]:
    next_action = {
        "label": label,
        "type": action_type,
        "style": style,
    }
    if value is not None:
        next_action["value"] = value
    return next_action


def step(
    step_id: str,
    title: str,
    detail: str,
    status: str,
    *,
    actions: list[dict[str, Any]] | None = None,
    extras: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": step_id,
        "title": title,
        "detail": detail,
        "status": status,
        "actions": actions or [],
        "extras": extras or [],
    }
