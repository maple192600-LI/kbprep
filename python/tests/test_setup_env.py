import subprocess
import unittest
from unittest.mock import patch

from kbprep_worker import setup_env


class SetupEnvTests(unittest.TestCase):
    def test_suggest_mineru_backend_from_hardware(self) -> None:
        self.assertEqual(setup_env.suggest_mineru_backend({"available": False})[0], "pipeline")
        self.assertEqual(
            setup_env.suggest_mineru_backend({"available": True, "vram_gb": 16, "device_name": "RTX"})[0],
            "hybrid-engine",
        )
        self.assertEqual(
            setup_env.suggest_mineru_backend({"available": True, "vram_gb": 6, "device_name": "RTX"})[0],
            "pipeline",
        )

    def test_choose_mineru_backend_honors_valid_override(self) -> None:
        payload, actions = setup_env.choose_mineru_backend(
            {"available": True, "vram_gb": 16, "device_name": "RTX"},
            "pipeline",
        )

        self.assertEqual(payload["suggested"], "hybrid-engine")
        self.assertEqual(payload["chosen"], "pipeline")
        self.assertEqual(actions, [])

    def test_choose_mineru_backend_reports_invalid_override(self) -> None:
        payload, actions = setup_env.choose_mineru_backend(
            {"available": True, "vram_gb": 16, "device_name": "RTX"},
            "missing-backend",
        )

        self.assertEqual(payload["suggested"], "hybrid-engine")
        self.assertEqual(payload["chosen"], "hybrid-engine")
        self.assertEqual(actions, ["invalid_backend_override:missing-backend"])

    def test_setup_gpu_installs_cuda_torch_before_mineru_all(self) -> None:
        calls: list[list[str]] = []

        def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess:
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        with patch("kbprep_worker.setup_env.check_nvidia_driver", return_value=True), \
            patch(
                "kbprep_worker.setup_env.probe_torch",
                side_effect=[
                    {"installed": True, "cuda_available": False, "device": "cpu"},
                    {"installed": True, "cuda_available": True, "device": "cuda", "version": "2.8.0+cu126"},
                ],
            ), \
            patch(
                "kbprep_worker.setup_env.get_gpu_info",
                return_value={"available": True, "vram_gb": 16, "device_name": "RTX"},
            ), \
            patch("kbprep_worker.setup_env.subprocess.run", side_effect=fake_run):
            result = setup_env.setup_gpu("venv-python", install_mineru=True)

        pip_calls = [cmd for cmd in calls if cmd[:3] == ["venv-python", "-m", "pip"]]
        self.assertEqual(len(pip_calls), 2)
        self.assertIn("torch==2.8.0", pip_calls[0])
        self.assertIn("--index-url", pip_calls[0])
        self.assertTrue(any(package.startswith("mineru[all]") for package in pip_calls[1]))
        self.assertEqual(result["actions_taken"], ["installed_cuda_torch", "installed_mineru_all"])
        self.assertEqual(result["mineru_backend"]["chosen"], "hybrid-engine")


if __name__ == "__main__":
    unittest.main()
