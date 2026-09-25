import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import cv2
import numpy as np

from qc_station.fixed_layout import CAT_LAYOUT, create_color_profile, sample_colors
from qc_station.variants import VARIANTS, inspect_variants, validate_variant_profile
from qc_station.vision import load_profile
from qc_station.diagnostics import save_detection


COLORS = {"red": (20, 30, 210), "yellow": (10, 220, 240),
          "blue": (210, 120, 20), "background": (60, 60, 60)}


def samples():
    return {name: np.tile(color, (100, 1)).astype(np.uint8) for name, color in COLORS.items()}


def scene(variant="A"):
    frame = np.full((480, 640, 3), COLORS["background"], np.uint8)
    for polygon, color in zip(CAT_LAYOUT["polygons"], VARIANTS[variant]):
        cv2.fillPoly(frame, [np.asarray(polygon, np.int32)], COLORS[color])
    return frame


class FixedLayoutTests(unittest.TestCase):
    def setUp(self):
        self.profile = create_color_profile(np.zeros((480, 640, 3), np.uint8), samples())

    def test_sampling_does_not_require_a_complete_good_product(self):
        self.assertEqual(self.profile["geometry_mode"], "fixed")
        self.assertFalse(inspect_variants(np.zeros((480, 640, 3), np.uint8), self.profile)[0]["passed"])

    def test_diagnostics_preserves_raw_frame_profile_and_measurement(self):
        frame = scene()
        result, mask = inspect_variants(frame, self.profile)
        with tempfile.TemporaryDirectory() as directory:
            folder = save_detection(frame, self.profile, result, mask, directory)
            self.assertTrue(np.array_equal(cv2.imread(str(folder/'frame.png')), frame))
            self.assertEqual(json.loads((folder/'result.json').read_text()), result)
            self.assertEqual(json.loads((folder/'profile.json').read_text()), self.profile)
            self.assertTrue((folder/'candidates.png').is_file())

    def test_all_variants_and_expected_variant_are_checked(self):
        for variant in "ABCD":
            result, _ = inspect_variants(scene(variant), self.profile, variant)
            self.assertTrue(result["passed"], result)
            self.assertEqual(result["detected_variant"], variant)
        self.assertFalse(inspect_variants(scene("B"), self.profile, "A")[0]["passed"])

    def test_missing_part_and_rotated_part_fail(self):
        for kind in ("missing", "rotated", "wrong_shape"):
            frame = scene()
            polygon = np.asarray(CAT_LAYOUT["polygons"][4], np.int32)
            cv2.fillPoly(frame, [polygon], COLORS["background"])
            if kind == "rotated":
                rotated = cv2.transform(polygon.reshape(-1, 1, 2).astype(np.float32),
                    cv2.getRotationMatrix2D(tuple(polygon.mean(axis=0)), 22, 1)).astype(np.int32)
                cv2.fillPoly(frame, [rotated], COLORS["red"])
            elif kind == "wrong_shape":
                cv2.rectangle(frame, (280, 260), (342, 315), COLORS["red"], -1)
            self.assertFalse(inspect_variants(frame, self.profile)[0]["passed"], kind)

    def test_full_circle_all_variants(self):
        for variant in VARIANTS:
            for angle in (0, 17, 45, 90, 137, 180, 225, 270, 319):
                matrix = cv2.getRotationMatrix2D((330, 240), angle, .75)
                frame = cv2.warpAffine(scene(variant), matrix, (640, 480),
                                       borderValue=COLORS["background"])
                result, _ = inspect_variants(frame, self.profile, variant)
                self.assertTrue(result["passed"], (variant, angle, result))
                self.assertEqual(result["detected_variant"], variant)

    def test_global_translation_is_accepted(self):
        frame = cv2.warpAffine(scene(), np.float32([[1, 0, -12], [0, 1, 6]]), (640, 480),
                               borderValue=COLORS["background"])
        self.assertTrue(inspect_variants(frame, self.profile)[0]["passed"])

    def test_learned_geometry_also_accepts_full_rotation(self):
        profile = copy.deepcopy(self.profile)
        profile["geometry_mode"] = "learned"
        for angle in (41, 90, 180, 270):
            frame = cv2.warpAffine(scene(), cv2.getRotationMatrix2D((330, 240), angle, .75),
                                   (640, 480), borderValue=COLORS["background"])
            self.assertTrue(inspect_variants(frame, profile)[0]["passed"], angle)

    def test_rotated_product_with_remote_background(self):
        frame = cv2.warpAffine(scene(), cv2.getRotationMatrix2D((330, 240), 90, .75),
                               (640, 480), borderValue=COLORS["background"])
        cv2.rectangle(frame, (100, 30), (115, 440), COLORS["blue"], -1)
        result, _ = inspect_variants(frame, self.profile)
        self.assertTrue(result["passed"], result["reasons"])
        self.assertEqual(result["found_count"], 7)

    def test_rotation_does_not_hide_defects_or_reflection(self):
        for kind in ("missing", "rotated", "displaced", "reflection", "wrong_variant"):
            frame = scene()
            polygon = np.asarray(CAT_LAYOUT["polygons"][4], np.int32)
            if kind in ("missing", "rotated", "displaced"):
                cv2.fillPoly(frame, [polygon], COLORS["background"])
                if kind == "rotated":
                    polygon = cv2.transform(polygon.reshape(-1, 1, 2).astype(np.float32),
                        cv2.getRotationMatrix2D(tuple(polygon.mean(axis=0)), 22, 1)).astype(np.int32)
                elif kind == "displaced":
                    polygon = polygon + [35, 0]
                if kind != "missing":
                    cv2.fillPoly(frame, [polygon], COLORS["red"])
            if kind == "reflection":
                frame = cv2.flip(frame, 1)
            for angle in (37, 90, 213):
                rotated = cv2.warpAffine(frame, cv2.getRotationMatrix2D((330, 240), angle, .75),
                                        (640, 480), borderValue=COLORS["background"])
                result, _ = inspect_variants(rotated, self.profile, "B" if kind == "wrong_variant" else "A")
                self.assertFalse(result["passed"], (kind, angle))

    def test_blue_board_components_outside_search_locations_are_ignored(self):
        frame = scene()
        # A disconnected rim, not touching the ROI itself; would be an extra blue contour.
        cv2.rectangle(frame, (100, 190), (125, 450), COLORS["blue"], -1)
        cv2.rectangle(frame, (128, 453), (545, 467), COLORS["blue"], -1)
        result, _ = inspect_variants(frame, self.profile)
        self.assertTrue(result["passed"], result)
        self.assertEqual(result["found_count"], 7)

    def test_background_cannot_be_cut_into_template_parts(self):
        frame = np.full((480, 640, 3), COLORS["blue"], np.uint8)
        self.assertFalse(inspect_variants(frame, self.profile)[0]["passed"])
        frame = scene()
        cv2.rectangle(frame, (205, 315), (470, 447), COLORS["blue"], -1)
        self.assertFalse(inspect_variants(frame, self.profile)[0]["passed"])

    def test_extra_piece_inside_search_area_is_not_silently_discarded(self):
        frame = scene()
        cv2.rectangle(frame, (267, 367), (293, 397), COLORS["red"], -1)
        self.assertFalse(inspect_variants(frame, self.profile)[0]["passed"])

    def test_fixed_profile_validation_and_resolution(self):
        bad = copy.deepcopy(self.profile)
        bad["parts"][0]["contour"][0][0] = [0, 0]
        with self.assertRaises(ValueError):
            validate_variant_profile(bad)
        with self.assertRaises(ValueError):
            inspect_variants(np.zeros((240, 320, 3), np.uint8), self.profile)

    def test_ui_saves_color_samples_without_corner_clicks_or_reference_pass(self):
        frame = np.zeros((480, 640, 3), np.uint8)
        regions = []
        for i, color in enumerate(COLORS.values()):
            x = 10+i*30
            frame[10:20, x:x+10] = color
            regions.append(np.array([[x, 10, 10, 10]]))
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)/"colors.json"
            with patch("qc_station.fixed_layout.cv2.imread", return_value=frame), \
                 patch("qc_station.fixed_layout.cv2.selectROIs", side_effect=regions) as select, \
                 patch("qc_station.fixed_layout.cv2.imshow"), \
                 patch("qc_station.fixed_layout.cv2.destroyWindow"), \
                 patch("qc_station.fixed_layout.cv2.destroyAllWindows"), \
                 patch("qc_station.fixed_layout.cv2.waitKey", return_value=ord("s")), patch("builtins.print"):
                sample_colors(0, str(target), image="test.png")
            self.assertEqual(select.call_count, 4)
            restored = load_profile(target)
            self.assertEqual(restored["geometry_mode"], "fixed")
            self.assertFalse(inspect_variants(frame, restored)[0]["passed"])
            self.assertTrue(inspect_variants(scene(), restored)[0]["passed"])
