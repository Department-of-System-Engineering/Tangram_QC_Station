import copy
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import cv2
import numpy as np

from qc_station.variants import (PART_NAMES, VARIANTS, create_variant_profile,
                                inspect_variants, angle_difference, validate_variant_profile)
from qc_station.vision import inspect, validate_profile
from qc_station.session import InspectionWindow
from qc_station.order_context import OrderContext
from qc_station.__main__ import run
from qc_station.storage import ResultStore


def scene(variant="A", background=(65, 65, 65), move=None):
    image = np.full((480, 640, 3), background, np.uint8)
    points = [
        [(40, 30), (92, 90), (40, 142)],
        [(104, 90), (155, 30), (155, 142)],
        [(98, 98), (148, 150), (98, 202), (46, 150)],
        [(184, 132), (250, 132), (181, 204), (115, 204)],
        [(260, 140), (260, 276), (193, 210)],
        [(275, 140), (382, 247), (275, 355)],
        [(390, 265), (390, 410), (240, 410)],
    ]
    colors = {label: cv2.cvtColor(np.uint8([[[hue, 230, 220]]]), cv2.COLOR_HSV2BGR)[0, 0].tolist()
              for label, hue in (("red", 0), ("yellow", 30), ("blue", 110))}
    polygons = []
    for i, pts in enumerate(points):
        c = np.array(pts, np.int32).reshape(-1, 1, 2) + [100, 10]
        if move and i == move[0]:
            c = c + move[1]
        polygons.append(c.astype(np.int32))
        cv2.fillPoly(image, [c.astype(np.int32)], colors[VARIANTS[variant][i]])
    return image, polygons


class VariantTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        image, polygons = scene()
        cls.profile = create_variant_profile(image, polygons, "A", [80, 10, 450, 445])

    def test_all_four_variants_and_nonpink_bases(self):
        for variant in VARIANTS:
            for bg in ((65, 65, 65), (210, 210, 210), (160, 80, 160), (220, 30, 20)):
                image, _ = scene(variant, bg)
                result, _ = inspect(image, self.profile)
                self.assertTrue(result["passed"], (variant, bg, result["reasons"], result["parts"]))
                self.assertEqual(result["detected_variant"], variant)
                self.assertGreater(result["quality_score"], 85)

    def test_wrong_order_does_not_override_recognition(self):
        image, _ = scene("B")
        result, _ = inspect(image, self.profile, "A")
        self.assertEqual(result["detected_variant"], "B")
        self.assertFalse(result["passed"])
        self.assertIn("variant_mismatch", result["reasons"])

    def test_calibrate_from_each_variant(self):
        for variant in VARIANTS:
            image, polygons = scene(variant)
            profile = create_variant_profile(image, polygons, variant, [80, 10, 450, 445])
            other, _ = scene("D" if variant != "D" else "A")
            self.assertTrue(inspect(other, profile)[0]["passed"])

    def test_empty_and_touching_same_color_pieces_do_not_pass(self):
        empty = np.full((480, 640, 3), 65, np.uint8)
        result, _ = inspect(empty, self.profile)
        self.assertFalse(result["object_present"])
        image, _ = scene()
        cv2.line(image, (430, 315), (440, 350), tuple(map(int, image[260, 410])), 12)
        self.assertFalse(inspect(image, self.profile)[0]["passed"])

    def test_unknown_color_combination(self):
        image, polygons = scene("A")
        cv2.fillPoly(image, [polygons[6]], (0, 220, 220))
        result, _ = inspect(image, self.profile)
        self.assertIsNone(result["detected_variant"])
        self.assertFalse(result["passed"])

    def test_missing_and_extra_piece(self):
        image, polygons = scene()
        cv2.fillPoly(image, [polygons[0]], (65, 65, 65))
        self.assertFalse(inspect(image, self.profile)[0]["passed"])
        image, _ = scene()
        cv2.rectangle(image, (100, 290), (135, 330), (20, 20, 220), -1)
        self.assertFalse(inspect(image, self.profile)[0]["passed"])

    def test_relative_displacement(self):
        image, _ = scene(move=(0, [25, 0]))
        result, _ = inspect(image, self.profile)
        self.assertFalse(result["passed"])
        self.assertTrue("relative_position" in result["reasons"] or any("position" in p["reasons"] for p in result["parts"]))

    def test_individual_rotation_reduces_angle_score(self):
        image, polygons = scene()
        baseline, _ = inspect(image, self.profile)
        c = polygons[4]
        cv2.fillPoly(image, [c], (65, 65, 65))
        center = tuple(c.reshape(-1, 2).mean(axis=0))
        rotated = cv2.transform(c.astype(np.float32), cv2.getRotationMatrix2D(center, 17, 1))
        cv2.fillPoly(image, [rotated.astype(np.int32)], (22, 22, 220))
        result, _ = inspect(image, self.profile)
        self.assertFalse(result["passed"])
        self.assertIn("edge_relations", result["reasons"])
        self.assertLess(result["scores"]["edge_relations"], baseline["scores"]["edge_relations"])

    def test_parallel_perpendicular_are_distinct(self):
        self.assertEqual(angle_difference(0, 180), 0)
        self.assertEqual(angle_difference(0, 90), 90)
        self.assertEqual(angle_difference(179, 1), 2)

    def test_small_global_rotation_translation(self):
        image, _ = scene()
        transform = cv2.getRotationMatrix2D((320, 240), 4, .94)
        transform[:, 2] += [5, 0]
        image = cv2.warpAffine(image, transform, (640, 480), borderValue=(65, 65, 65))
        result, _ = inspect(image, self.profile)
        self.assertTrue(result["passed"], (result["reasons"], result["parts"]))

    def test_profile_and_work_area_validation(self):
        validate_profile(self.profile)
        invalid = copy.deepcopy(self.profile)
        invalid["relations"] = []
        with self.assertRaises(ValueError):
            validate_variant_profile(invalid)
        with self.assertRaises(ValueError):
            inspect(np.zeros((240, 320, 3), np.uint8), self.profile)

    def test_mixed_variant_window_cannot_pass(self):
        window = InspectionWindow()
        for i in range(31):
            result = {"base_present": True, "passed": True, "parts": [], "reasons": [],
                      "detected_variant": "A" if i < 15 else "B", "expected_variant": None,
                      "quality_score": 98}
            final = window.update(result, i/10)
        self.assertEqual(final["status"], "INCONCLUSIVE")
        self.assertIsNone(final["detected_variant"])

    def test_order_context(self):
        payload = {"order_id": 1, "product_instance_id": 42, "expected_variant": "D"}
        self.assertEqual(OrderContext.from_dict(payload).expected_variant, "D")
        for key, value in (("order_id", True), ("product_instance_id", -1), ("expected_variant", "E")):
            with self.assertRaises(ValueError):
                OrderContext.from_dict({**payload, key: value})

    def test_order_driven_runtime_saves_identity_and_rejects_wrong_variant(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_path = folder / "profile.json"
            profile_path.write_text(json.dumps(self.profile), encoding="utf-8")
            order_path = folder / "order.json"
            order_path.write_text(json.dumps({"order_id": 12, "product_instance_id": 123, "expected_variant": "A"}), encoding="utf-8")
            args = SimpleNamespace(profile=str(profile_path), fps=10, width=640, height=480,
                product_instance_id=None, expected_variant=None, once=True, seconds=3,
                min_samples=15, camera="0", output=directory, no_video=True, max_videos=10,
                station_id="test", headless=True, debug=False, order_context=str(order_path))
            image, _ = scene("B")
            with patch("qc_station.__main__.cv2.VideoCapture") as capture, \
                 patch("qc_station.__main__.time.monotonic", side_effect=[i*.11 for i in range(100)]), \
                 patch("builtins.print"):
                capture.return_value.isOpened.return_value = True
                capture.return_value.read.side_effect = [(True, image.copy()) for _ in range(100)]
                run(args)
            store = ResultStore(folder / "delivery")
            try:
                event = store.events()[0]
            finally:
                store.close()
            self.assertEqual(event["order_id"], 12)
            self.assertEqual(event["product_instance_id"], 123)
            self.assertEqual(event["expected_variant"], "A")
            self.assertEqual(event["result"]["detected_variant"], "B")
            self.assertEqual(event["result"]["status"], "FAIL")
            args.once = False
            with self.assertRaises(ValueError), patch("qc_station.__main__.cv2.VideoCapture") as capture:
                run(args)
            capture.assert_not_called()


if __name__ == "__main__":
    unittest.main()
