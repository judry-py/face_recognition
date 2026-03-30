import unittest

import numpy as np

from surveillance_app.config import AppConfig
from surveillance_app.vision import detect_people, evaluate_suspicious_activity


class VisionMlTests(unittest.TestCase):
    def test_detect_people_returns_empty_list_on_blank_frame(self):
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        detections = detect_people(frame, AppConfig())
        self.assertEqual(detections, [])

    def test_evaluate_suspicious_activity_requires_human_for_motion_alerts(self):
        config = AppConfig(require_human_for_motion_alert=True, suspicious_motion_frames=3)

        suspicious, reason = evaluate_suspicious_activity(
            motion_streak=4,
            motion_ratio=0.12,
            suspicious_threshold=0.08,
            unknown_present=False,
            human_present=False,
            config=config,
        )
        self.assertFalse(suspicious)
        self.assertEqual(reason, "")

        suspicious, reason = evaluate_suspicious_activity(
            motion_streak=4,
            motion_ratio=0.12,
            suspicious_threshold=0.08,
            unknown_present=False,
            human_present=True,
            config=config,
        )
        self.assertTrue(suspicious)
        self.assertIn("humain", reason.lower())

    def test_unknown_face_remains_priority_alert(self):
        config = AppConfig(require_human_for_motion_alert=True)
        suspicious, reason = evaluate_suspicious_activity(
            motion_streak=1,
            motion_ratio=0.01,
            suspicious_threshold=0.08,
            unknown_present=True,
            human_present=False,
            config=config,
        )
        self.assertTrue(suspicious)
        self.assertIn("inconnu", reason.lower())


if __name__ == "__main__":
    unittest.main()
