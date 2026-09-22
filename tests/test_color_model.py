import copy
import tempfile
from pathlib import Path
import unittest
import cv2
import numpy as np

from test_variants import scene
from qc_station.variants import create_variant_profile, inspect_variants, ReferenceValidationError
from qc_station.color_model import palette_masks, validate_palette
from qc_station.calibration_diagnostics import save_diagnostics, load_selection
from qc_station.vision import load_profile


def bgr(hsv):
    return tuple(map(int, cv2.cvtColor(np.uint8([[hsv]]), cv2.COLOR_HSV2BGR)[0, 0]))


class ColorModelTests(unittest.TestCase):
    def test_pale_red_on_similar_pink_background(self):
        frame, polygons = scene(background=bgr([163, 84, 200]))
        cv2.fillPoly(frame, [polygons[2]], bgr([164, 55, 185]))
        cv2.fillPoly(frame, [polygons[4]], bgr([173, 85, 177]))
        profile = create_variant_profile(frame, polygons, "A", [80, 10, 450, 445])
        self.assertTrue(inspect_variants(frame, profile)[0]["passed"])
        legacy = copy.deepcopy(profile)
        legacy.pop("color_model")
        self.assertFalse(inspect_variants(frame, legacy)[0]["passed"])
        cv2.fillPoly(frame, [polygons[2]], bgr([163, 84, 200]))
        self.assertFalse(inspect_variants(frame, profile)[0]["passed"])

    def test_background_cannot_be_claimed_as_a_piece_by_tie(self):
        centers = {c: [[100, 128, 128]] for c in ("red", "yellow", "blue", "background")}
        model = {"space": "LAB", "centers": centers,
                 "max_distance_squared": {c: 1000 for c in centers}}
        validate_palette(model)
        masks = palette_masks(np.full((30, 30, 3), 100, np.uint8), model)
        self.assertTrue(all(not np.any(mask) for mask in masks.values()))

    def test_diagnostics_preserve_raw_frame_and_resume_selection(self):
        frame, polygons = scene()
        roi = [80, 10, 450, 445]
        profile = create_variant_profile(frame, polygons, "A", roi)
        broken = frame.copy()
        cv2.fillPoly(broken, [polygons[2]], (65, 65, 65))
        result, mask = inspect_variants(broken, profile)
        error = ReferenceValidationError("reference rejected", profile, result, mask)
        with tempfile.TemporaryDirectory() as directory:
            folder = save_diagnostics(Path(directory)/"active.json", broken, polygons, "A", roi, error)
            restored, selected, variant, saved_roi = load_selection(folder/"selection.json")
            np.testing.assert_array_equal(restored, broken)
            for a, b in zip(selected, polygons):
                np.testing.assert_array_equal(a, b)
            self.assertEqual(variant, "A")
            self.assertEqual(saved_roi, roi)
            self.assertFalse((Path(directory)/"active.json").exists())
            with self.assertRaises(ValueError):
                load_profile(folder/"report.json")
            self.assertTrue((folder/"detected.png").exists())

    def test_invalid_palette_rejected(self):
        frame, polygons = scene()
        profile = create_variant_profile(frame, polygons, "A", [80, 10, 450, 445])
        profile["color_model"]["centers"]["red"] = [[float("nan"), 0, 0]]
        with self.assertRaises(ValueError):
            validate_palette(profile["color_model"])


if __name__ == "__main__":
    unittest.main()
