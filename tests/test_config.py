import json
import os
import tempfile
import unittest
from datetime import time
from pathlib import Path

from surveillance_app.config import AppConfig, build_dashboard_url, ensure_directories, load_config
from surveillance_app.utils import is_time_in_window


class ConfigAndUtilsTests(unittest.TestCase):
    def test_load_config_applies_json_and_env_overrides(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "config.json"
            config_path.write_text(
                json.dumps({"camera_index": 1, "dashboard_port": 5050, "admin_password": "json-pass"}),
                encoding="utf-8",
            )

            original_camera = os.environ.get("SURVEILLANCE_CAMERA_INDEX")
            os.environ["SURVEILLANCE_CAMERA_INDEX"] = "3"
            try:
                config = load_config(config_path)
            finally:
                if original_camera is None:
                    os.environ.pop("SURVEILLANCE_CAMERA_INDEX", None)
                else:
                    os.environ["SURVEILLANCE_CAMERA_INDEX"] = original_camera

            self.assertEqual(config.camera_index, 3)
            self.assertEqual(config.dashboard_port, 5050)
            self.assertEqual(config.admin_password, "json-pass")

    def test_ensure_directories_creates_expected_folders(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = AppConfig(
                faces_dir=str(root / "faces"),
                alerts_dir=str(root / "alerts"),
                captures_dir=str(root / "captures"),
                reports_dir=str(root / "reports"),
            )

            ensure_directories(config)

            self.assertTrue((root / "faces").exists())
            self.assertTrue((root / "alerts").exists())
            self.assertTrue((root / "captures").exists())
            self.assertTrue((root / "reports").exists())

    def test_helpers_build_url_and_handle_time_windows(self):
        config = AppConfig(dashboard_host="localhost", dashboard_port=8080)
        self.assertEqual(build_dashboard_url(config), "http://localhost:8080")
        self.assertTrue(is_time_in_window("08:00", "18:00", time(12, 0)))
        self.assertFalse(is_time_in_window("08:00", "18:00", time(22, 0)))
        self.assertTrue(is_time_in_window("22:00", "06:00", time(1, 30)))


if __name__ == "__main__":
    unittest.main()
