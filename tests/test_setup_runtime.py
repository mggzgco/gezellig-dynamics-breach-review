"""Regression tests for setup runtime status caching."""

from __future__ import annotations

from unittest import TestCase, mock

from app.setup_runtime import SetupRuntimeCoordinator
from app.setup_runtime_modules.models import DEPENDENCY_OCR, DEPENDENCY_OLLAMA, InstallSpec


class _CountingSetupRuntimeCoordinator(SetupRuntimeCoordinator):
    def __init__(self) -> None:
        super().__init__()
        self.structured_call_count = 0

    def _ollama_service_status(self):
        return True, "Ollama is reachable.", {"models": [{"name": "qwen3:4b"}]}

    def _structured_generation_status(self):
        self.structured_call_count += 1
        return True, "Structured generation probe succeeded."


class _FailingStructuredSetupRuntimeCoordinator(_CountingSetupRuntimeCoordinator):
    def _structured_generation_status(self):
        self.structured_call_count += 1
        return False, "Structured generation probe failed."


class SetupRuntimeTests(TestCase):
    @mock.patch("app.setup_runtime._upload_dir_status", return_value=(True, "Upload directory OK"))
    @mock.patch("app.setup_runtime._command_status", return_value=(True, "dependency ok"))
    @mock.patch("app.setup_runtime.LOCAL_LLM_PROVIDER", "ollama")
    @mock.patch("app.setup_runtime.LOCAL_LLM_ENABLED", True)
    def test_basic_status_reuses_last_successful_deep_check(self, _mock_command_status, _mock_upload_dir_status):
        coordinator = _CountingSetupRuntimeCoordinator()

        deep_payload = coordinator.get_status(deep=True)
        self.assertTrue(deep_payload["checks"]["structured_generation"]["ok"])
        self.assertEqual(coordinator.structured_call_count, 1)

        basic_payload = coordinator.get_status(deep=False)
        self.assertTrue(basic_payload["checks"]["structured_generation"]["ok"])
        self.assertEqual(
            basic_payload["checks"]["structured_generation"]["detail"],
            "Structured generation probe succeeded.",
        )
        self.assertEqual(coordinator.structured_call_count, 1)

    @mock.patch("app.setup_runtime._upload_dir_status", return_value=(True, "Upload directory OK"))
    @mock.patch("app.setup_runtime._command_status", return_value=(True, "dependency ok"))
    @mock.patch("app.setup_runtime.LOCAL_LLM_PROVIDER", "ollama")
    @mock.patch("app.setup_runtime.LOCAL_LLM_ENABLED", True)
    def test_basic_status_without_cache_requests_validation_message(self, _mock_command_status, _mock_upload_dir_status):
        coordinator = _CountingSetupRuntimeCoordinator()

        basic_payload = coordinator.get_status(deep=False)
        self.assertFalse(basic_payload["checks"]["structured_generation"]["ok"])
        self.assertIn(
            "Run the system check",
            basic_payload["checks"]["structured_generation"]["detail"],
        )
        self.assertEqual(coordinator.structured_call_count, 0)

    @mock.patch("app.setup_runtime._upload_dir_status", return_value=(True, "Upload directory OK"))
    @mock.patch("app.setup_runtime._command_status", return_value=(True, "dependency ok"))
    @mock.patch("app.setup_runtime.LOCAL_LLM_PROVIDER", "ollama")
    @mock.patch("app.setup_runtime.LOCAL_LLM_ENABLED", True)
    def test_ready_status_exposes_ui_contract(self, _mock_command_status, _mock_upload_dir_status):
        coordinator = _CountingSetupRuntimeCoordinator()

        payload = coordinator.get_status(deep=True)

        self.assertTrue(payload["wizard_ready"])
        self.assertEqual(payload["ui"]["state"], "ready")
        self.assertEqual(payload["ui"]["banner"]["label"], "System ready")
        self.assertFalse(payload["ui"]["workspace_locked"])
        self.assertEqual(payload["ui"]["wizard_primary_actions"][0]["type"], "continue")

    @mock.patch("app.setup_runtime._upload_dir_status", return_value=(True, "Upload directory OK"))
    @mock.patch("app.setup_runtime._command_status", return_value=(True, "dependency ok"))
    @mock.patch("app.setup_runtime.LOCAL_LLM_PROVIDER", "ollama")
    @mock.patch("app.setup_runtime.LOCAL_LLM_ENABLED", True)
    def test_startup_prime_populates_basic_status_with_structured_validation(
        self,
        _mock_command_status,
        _mock_upload_dir_status,
    ):
        coordinator = _CountingSetupRuntimeCoordinator()

        coordinator.prime_structured_generation_check()
        payload = coordinator.get_status(deep=False)

        self.assertEqual(coordinator.structured_call_count, 1)
        self.assertTrue(payload["checks"]["structured_generation"]["ok"])
        self.assertTrue(payload["wizard_ready"])
        self.assertEqual(payload["ui"]["state"], "ready")

    @mock.patch("app.setup_runtime._upload_dir_status", return_value=(True, "Upload directory OK"))
    @mock.patch("app.setup_runtime._command_status", return_value=(True, "dependency ok"))
    @mock.patch("app.setup_runtime.LOCAL_LLM_PROVIDER", "ollama")
    @mock.patch("app.setup_runtime.LOCAL_LLM_ENABLED", True)
    def test_failed_startup_prime_keeps_workspace_locked_on_basic_status(
        self,
        _mock_command_status,
        _mock_upload_dir_status,
    ):
        coordinator = _FailingStructuredSetupRuntimeCoordinator()

        coordinator.prime_structured_generation_check()
        payload = coordinator.get_status(deep=False)

        self.assertEqual(coordinator.structured_call_count, 1)
        self.assertFalse(payload["checks"]["structured_generation"]["ok"])
        self.assertFalse(payload["wizard_ready"])
        self.assertEqual(payload["ui"]["state"], "validation_failed")
        self.assertTrue(payload["ui"]["workspace_locked"])

    @mock.patch("app.setup_runtime._upload_dir_status", return_value=(True, "Upload directory OK"))
    @mock.patch("app.setup_runtime._command_status", return_value=(False, "ollama is not installed"))
    @mock.patch("app.setup_runtime._resolve_install_spec", return_value=None)
    def test_missing_ollama_exposes_install_state_actions(
        self,
        _mock_resolve_install_spec,
        _mock_command_status,
        _mock_upload_dir_status,
    ):
        coordinator = SetupRuntimeCoordinator()

        payload = coordinator.get_status(deep=False)

        self.assertFalse(payload["wizard_ready"])
        self.assertEqual(payload["ui"]["state"], "install_ollama")
        self.assertTrue(payload["ui"]["workspace_locked"])
        gate_actions = payload["ui"]["workspace_gate"]["actions"]
        self.assertEqual(gate_actions[0]["type"], "external")
        self.assertEqual(gate_actions[0]["value"], "__OLLAMA_DOWNLOAD_URL__")

    @mock.patch("app.setup_runtime._upload_dir_status", return_value=(True, "Upload directory OK"))
    @mock.patch("app.setup_runtime._command_status", return_value=(False, "ollama is not installed"))
    @mock.patch(
        "app.setup_runtime._resolve_install_spec",
        return_value=InstallSpec(
            dependency=DEPENDENCY_OLLAMA,
            label="Ollama",
            command=["brew", "install", "ollama"],
            display_command="brew install ollama",
        ),
    )
    def test_missing_ollama_prefers_install_action_when_supported(
        self,
        _mock_resolve_install_spec,
        _mock_command_status,
        _mock_upload_dir_status,
    ):
        coordinator = SetupRuntimeCoordinator()

        payload = coordinator.get_status(deep=False)

        gate_actions = payload["ui"]["workspace_gate"]["actions"]
        self.assertEqual(gate_actions[0]["type"], "install-dependency")
        self.assertEqual(gate_actions[0]["value"], "ollama")

    @mock.patch("app.setup_runtime._upload_dir_status", return_value=(True, "Upload directory OK"))
    @mock.patch("app.setup_runtime._resolve_install_spec")
    def test_missing_ocr_prefers_install_action_when_supported(self, mock_resolve_install_spec, _mock_upload_dir_status):
        def fake_command_status(command, **_kwargs):
            if command[0] == "tesseract":
                return False, "tesseract is not installed"
            if command[0] == "ollama":
                return True, "ollama version is 0.0.0"
            return True, "ok"

        def fake_resolve_install_spec(dependency):
            if dependency == DEPENDENCY_OCR:
                return InstallSpec(
                    dependency=DEPENDENCY_OCR,
                    label="OCR support",
                    command=["brew", "install", "tesseract", "libmagic"],
                    display_command="brew install tesseract libmagic",
                )
            return None

        mock_resolve_install_spec.side_effect = fake_resolve_install_spec
        coordinator = SetupRuntimeCoordinator()

        with mock.patch.object(coordinator, "_ollama_service_status", return_value=(True, "Ollama reachable.", {"models": [{"name": "qwen3:4b"}]})):
            with mock.patch("app.setup_runtime._command_status", side_effect=fake_command_status):
                payload = coordinator.get_status(deep=False)

        self.assertEqual(payload["ui"]["state"], "install_ocr")
        gate_actions = payload["ui"]["workspace_gate"]["actions"]
        self.assertEqual(gate_actions[0]["type"], "install-dependency")
        self.assertEqual(gate_actions[0]["value"], "ocr")

    @mock.patch("app.setup_runtime._resolve_install_spec", return_value=None)
    def test_install_dependency_rejects_when_unsupported(self, _mock_resolve_install_spec):
        coordinator = SetupRuntimeCoordinator()

        accepted, payload = coordinator.start_dependency_install("ollama")

        self.assertFalse(accepted)
        self.assertIn("not supported", payload["message"])
