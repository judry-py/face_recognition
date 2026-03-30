import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from surveillance_app.config import AppConfig
from surveillance_app.dashboard_web import create_dashboard_app
from surveillance_app.services import append_csv_row, generate_html_report


class DashboardAndReportTests(unittest.TestCase):
    def test_status_endpoint_returns_expected_counts(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = AppConfig(
                alerts_dir=str(root / "alerts"),
                captures_dir=str(root / "captures"),
                reports_dir=str(root / "reports"),
                detections_log=str(root / "detections.csv"),
                alerts_log=str(root / "alerts.csv"),
                dashboard_host="127.0.0.1",
                dashboard_port=5000,
            )
            for folder in (root / "alerts", root / "captures", root / "reports"):
                folder.mkdir(parents=True, exist_ok=True)

            append_csv_row(
                config.detections_log,
                ["timestamp", "name", "confidence", "status"],
                {"timestamp": "2026-03-30 13:00:00", "name": "Alice", "confidence": "96.0", "status": "reconnu"},
            )
            append_csv_row(
                config.detections_log,
                ["timestamp", "name", "confidence", "status"],
                {"timestamp": "2026-03-30 13:01:00", "name": "Inconnu", "confidence": "0.0", "status": "inconnu"},
            )
            append_csv_row(
                config.alerts_log,
                ["timestamp", "reason", "motion_percent", "faces_detected", "snapshot", "video"],
                {"timestamp": "2026-03-30 13:02:00", "reason": "Visage inconnu détecté", "motion_percent": "12.5", "faces_detected": "Inconnu", "snapshot": "snap.jpg", "video": "alert.avi"},
            )

            with patch("surveillance_app.dashboard_web.load_config", return_value=config):
                app = create_dashboard_app()
                client = app.test_client()
                response = client.get("/api/status")

            self.assertEqual(response.status_code, 200)
            payload = response.get_json()
            self.assertEqual(payload["total_detections"], 2)
            self.assertEqual(payload["total_alerts"], 1)
            self.assertEqual(payload["unknown_detections"], 1)
            self.assertEqual(payload["known_people"], 1)

    def test_report_generation_creates_html_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = AppConfig(
                reports_dir=str(root / "reports"),
                detections_log=str(root / "detections.csv"),
                alerts_log=str(root / "alerts.csv"),
            )
            (root / "reports").mkdir(parents=True, exist_ok=True)

            report_path = generate_html_report(config)

            self.assertTrue(Path(report_path).exists())
            self.assertIn("Rapport de surveillance", Path(report_path).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
