import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import cv2
import numpy as np

from qc_station.vision import create_profile, inspect, learn_color, hsv_mask, validate_profile, extract, repair_mask
from qc_station.session import InspectionWindow
from qc_station.storage import ResultStore
from qc_station.__main__ import run


def fixture():
    image = np.zeros((480, 640, 3), np.uint8)
    pink = cv2.cvtColor(np.uint8([[[150, 180, 190]]]), cv2.COLOR_HSV2BGR)[0, 0].tolist()
    cv2.rectangle(image, (60, 50), (580, 420), pink, -1)
    for x, y in [(100, 100), (230, 100), (360, 100), (490, 100),
                 (140, 270), (300, 270), (460, 270)]:
        cv2.fillPoly(image, [np.array([[x, y], [x+55, y], [x, y+65]])], (0, 150, 240))
    return image


class VisionTests(unittest.TestCase):
    def setUp(self):
        self.image = fixture()
        self.profile = create_profile(self.image, [[140, 80, 60], [165, 255, 255]])

    def test_reference_and_scaled_translation_pass(self):
        validate_profile(self.profile)
        self.assertTrue(inspect(self.image, self.profile)[0]["passed"])
        moved = cv2.warpAffine(self.image, np.float32([[0.8, 0, 40], [0, 0.8, 20]]), (640, 480))
        self.assertTrue(inspect(moved, self.profile)[0]["passed"])

    def test_missing_part_fails(self):
        self.image[90:180, 90:170] = self.image[60, 70]
        self.assertFalse(inspect(self.image, self.profile)[0]["passed"])

    def test_wrong_color_fails(self):
        self.image[np.all(self.image == [0, 150, 240], axis=2)] = [200, 150, 0]
        result = inspect(self.image, self.profile)[0]
        self.assertFalse(result["passed"])
        self.assertTrue(any("color_fraction" in p["reasons"] for p in result["parts"]))

    def test_wrong_shape_and_position_fail(self):
        self.image[90:180, 90:170] = self.image[60, 70]
        cv2.rectangle(self.image, (110, 100), (160, 160), (0, 150, 240), -1)
        self.assertFalse(inspect(self.image, self.profile)[0]["passed"])

    def test_extra_part_fails(self):
        cv2.rectangle(self.image, (240, 210), (285, 250), (0, 150, 240), -1)
        self.assertFalse(inspect(self.image, self.profile)[0]["passed"])

    def test_empty_or_clipped_fails(self):
        self.assertFalse(inspect(np.zeros_like(self.image), self.profile)[0]["passed"])
        shifted = cv2.warpAffine(self.image, np.float32([[1, 0, -90], [0, 1, 0]]), (640, 480))
        self.assertFalse(inspect(shifted, self.profile)[0]["passed"])

    def test_red_wraparound(self):
        pixels = np.array([[h, 200, 200] for h in [0, 1, 178, 179]] * 20, np.uint8)
        bounds = learn_color(pixels)
        self.assertGreater(bounds[0][0], bounds[1][0])
        self.assertTrue((hsv_mask(pixels.reshape(1, -1, 3), bounds) > 0).all())

    def test_bad_calibration_rejected(self):
        with self.assertRaises(ValueError):
            create_profile(np.zeros_like(self.image), self.profile["base_hsv"])
        self.profile["thresholds"]["overlap"] = float("nan")
        with self.assertRaises(ValueError):
            validate_profile(self.profile)

    def test_two_broken_boundaries_recovered_in_calibration_and_inspection(self):
        bounds = self.profile["base_hsv"]
        for x in (110, 240):
            cv2.line(self.image, (x, 48), (x, 106), (0, 0, 0), 9)
        self.assertEqual(len(extract(self.image, bounds)[1]), 5)
        config = {"close_kernel": 3, "frame_size": [640, 480],
                  "bridges": [[[102, 80], [118, 80]], [[232, 80], [248, 80]]]}
        profile = create_profile(self.image, bounds, segmentation=config)
        validate_profile(profile)
        self.assertTrue(inspect(self.image, profile)[0]["passed"])
        self.image[90:180, 90:170] = self.image[60, 70]
        self.assertFalse(inspect(self.image, profile)[0]["passed"])
        self.assertFalse(inspect(np.zeros_like(self.image), profile)[0]["passed"])

    def test_closing_adjustment_is_used_in_inspection(self):
        for x in (110, 240):
            cv2.line(self.image, (x, 48), (x, 106), (0, 0, 0), 5)
        config = {"close_kernel": 9, "bridges": []}
        profile = create_profile(self.image, self.profile["base_hsv"], segmentation=config)
        validate_profile(profile)
        self.assertTrue(inspect(self.image, profile)[0]["passed"])

    def test_bridge_requires_both_visible_endpoints_and_same_resolution(self):
        mask = np.zeros((100, 100), np.uint8)
        mask[40:45, 20:25] = 255
        config = {"close_kernel": 3, "frame_size": [100, 100], "bridges": [[[22, 42], [40, 42]]]}
        self.assertEqual(repair_mask(mask, config)[42, 30], 0)
        mask[40:45, 38:43] = 255
        self.assertEqual(repair_mask(mask, config)[42, 30], 255)
        with self.assertRaises(ValueError):
            repair_mask(np.zeros((50, 50), np.uint8), config)

    def test_invalid_bridge_configuration_rejected(self):
        for config in ({"close_kernel": 4}, {"bridges": [[[0, 0], [100, 0]]], "frame_size": [640, 480]},
                       {"bridges": [[[-1, 20], [10, 20]]], "frame_size": [640, 480]}):
            self.profile["segmentation"] = config
            with self.assertRaises(ValueError):
                validate_profile(self.profile)


def observation(passed=True, present=True):
    return {"base_present": present, "passed": passed, "parts": [],
            "reasons": [] if passed else ["missing"]}


class WindowTests(unittest.TestCase):
    def test_full_window_and_latch(self):
        w = InspectionWindow()
        for i in range(30):
            self.assertIsNone(w.update(observation(), i / 10))
        self.assertEqual(w.update(observation(), 3)["status"], "PASS")
        self.assertIsNone(w.update(observation(), 4))
        w.update(observation(False, False), 5)
        w.update(observation(False, False), 5.8)
        self.assertIsNone(w.started)
        w.update(observation(), 6)
        self.assertEqual(w.samples, 1)

    def test_empty_frames_do_not_keep_old_pass(self):
        w = InspectionWindow()
        for i in range(30):
            w.update(observation(i < 10, i < 10), i / 10)
        self.assertEqual(w.update(observation(False, False), 3)["status"], "FAIL")

    def test_flicker_is_tolerated_but_last_frame_must_pass(self):
        for last, expected in [(True, "PASS"), (False, "FAIL")]:
            w = InspectionWindow()
            for i in range(30):
                w.update(observation(i not in (5, 12, 19)), i / 10)
            self.assertEqual(w.update(observation(last), 3)["status"], expected)

    def test_too_few_samples(self):
        w = InspectionWindow()
        w.update(observation(), 0)
        self.assertEqual(w.update(observation(), 3)["status"], "INCONCLUSIVE")

    def test_sampling_stall_prevents_pass(self):
        w = InspectionWindow()
        for i in range(20):
            w.update(observation(), i/20)
        self.assertEqual(w.update(observation(), 3)["status"], "INCONCLUSIVE")


class StoreTests(unittest.TestCase):
    def test_durable_retry_and_idempotency_header(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "results.db"
            store = ResultStore(path)
            store.save({"inspection_id": "unique", "result": {"status": "PASS"}})
            store.close()
            store = ResultStore(path)
            with patch("urllib.request.build_opener") as build:
                opener = build.return_value
                opener.open.side_effect = OSError("offline")
                with self.assertRaises(OSError):
                    store.flush("http://localhost/qc")
                self.assertEqual(store.db.execute("SELECT delivered FROM results").fetchone()[0], 0)
                opener.open.side_effect = None
                opener.open.return_value.__enter__.return_value.status = 202
                self.assertEqual(store.flush("http://localhost/qc"), 1)
                request = opener.open.call_args.args[0]
                self.assertEqual(request.get_header("Idempotency-key"), "unique")
                self.assertEqual(json.loads(request.data)["inspection_id"], "unique")
                self.assertEqual(store.flush("http://localhost/qc"), 0)
            store.close()


class RuntimeTests(unittest.TestCase):
    def run_camera(self, folder, fail=False, interrupt=False):
        frame = fixture()
        profile = create_profile(frame, [[140, 80, 60], [165, 255, 255]])
        path = Path(folder) / "profile.json"
        path.write_text(json.dumps(profile))
        args = SimpleNamespace(profile=str(path), fps=10, width=640, height=480,
            product_instance_id=123, once=True, seconds=3, min_samples=15,
            camera="0", output=folder, no_video=False, max_videos=10,
            station_id="test", headless=True, debug=False)
        with patch("qc_station.__main__.cv2.VideoCapture") as capture, \
             patch("qc_station.__main__.time.monotonic", side_effect=[i * 0.11 for i in range(100)]), \
             patch("builtins.print"):
            cap = capture.return_value
            cap.isOpened.return_value = True
            if fail:
                cap.read.side_effect = [(True, frame.copy()), (False, None)]
                with self.assertRaises(RuntimeError):
                    run(args)
            elif interrupt:
                cap.read.side_effect = [(True, frame.copy()), KeyboardInterrupt()]
                with self.assertRaises(KeyboardInterrupt):
                    run(args)
            else:
                cap.read.side_effect = [(True, frame.copy()) for _ in range(100)]
                run(args)
            cap.release.assert_called_once()
        store = ResultStore(Path(folder) / "results.sqlite3")
        rows = store.db.execute("SELECT payload FROM results").fetchall()
        store.close()
        self.assertEqual(len(rows), 1)
        return json.loads(rows[0][0])

    def test_complete_inspection_and_video(self):
        with tempfile.TemporaryDirectory() as d:
            event = self.run_camera(d)
            self.assertEqual(event["result"]["status"], "PASS")
            self.assertEqual(event["product_instance_id"], 123)
            clip = cv2.VideoCapture(event["video_path"])
            try:
                self.assertTrue(clip.isOpened())
                self.assertGreaterEqual(clip.get(cv2.CAP_PROP_FRAME_COUNT), 15)
                self.assertTrue(clip.read()[0])
            finally:
                clip.release()

    def test_camera_failure_and_interrupt_are_inconclusive(self):
        for mode in ("fail", "interrupt"):
            with tempfile.TemporaryDirectory() as d:
                event = self.run_camera(d, **{mode: True})
                self.assertEqual(event["result"]["status"], "INCONCLUSIVE")


if __name__ == "__main__":
    unittest.main()
