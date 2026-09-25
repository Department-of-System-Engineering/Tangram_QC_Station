import unittest
import json
from pathlib import Path
import cv2
import numpy as np

from test_variants import scene
from qc_station.variants import create_variant_profile, inspect_variants, fit_edge_polygon, edges, edge_correspondence, angle_difference


class ContourRobustnessTests(unittest.TestCase):
    def test_reported_body_mask_has_measurable_sides_at_pixel_and_normalized_scale(self):
        raw = np.asarray(json.loads((Path(__file__).parent / "fixtures/body_mask_20260924.json").read_text()), np.float32)
        for scale in (1, 1/480):
            contour = raw*scale
            before = contour.copy()
            fitted = fit_edge_polygon(contour, 3)
            self.assertIsNotNone(fitted)
            self.assertTrue(np.array_equal(contour, before))
            self.assertLess(abs(cv2.contourArea(fitted)/cv2.contourArea(contour)-1), .12)

    def test_limited_mask_dropout_preserves_orientation_measurement(self):
        mask = np.zeros((170, 250), np.uint8)
        reference = np.array([[10, 10], [230, 10], [110, 140]], np.float32).reshape(-1, 1, 2)
        cv2.fillPoly(mask, [reference.astype(np.int32)], 255)
        cv2.rectangle(mask, (50, 0), (64, 24), 0, -1)
        cv2.rectangle(mask, (125, 0), (139, 24), 0, -1)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        raw = contours[0].astype(np.float32)
        for observed in (raw, raw[::-1].copy(), np.roll(raw, 12, axis=0)):
            mapped = edge_correspondence(reference, observed)
            self.assertIsNotNone(mapped)
            self.assertLess(max(angle_difference(a[0], b[0]) for a, b in zip(edges(reference), mapped)), 2)
        rotated = cv2.transform(raw, cv2.getRotationMatrix2D((120, 80), 15, 1))
        mapped = edge_correspondence(reference, rotated)
        self.assertIsNotNone(mapped)
        self.assertGreater(max(angle_difference(a[0], b[0]) for a, b in zip(edges(reference), mapped)), 12)

    def test_deep_or_extensive_triangle_loss_does_not_get_invented_edges(self):
        for left, right, depth in ((70, 90, 55), (35, 205, 25)):
            mask = np.zeros((170, 250), np.uint8)
            cv2.fillPoly(mask, [np.array([[10, 10], [230, 10], [110, 140]])], 255)
            cv2.rectangle(mask, (left, 0), (right, depth), 0, -1)
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            self.assertIsNone(fit_edge_polygon(contours[0], 3))

    def test_tiny_background_components_are_not_parts(self):
        frame, polygons = scene()
        profile = create_variant_profile(frame, polygons, "A", [80, 10, 450, 445])
        color = tuple(map(int, frame[80, 150]))
        for y in (250, 290, 330, 370):
            cv2.circle(frame, (110, y), 10, color, -1)
        result, mask = inspect_variants(frame, profile)
        self.assertEqual(result["found_count"], 7)
        self.assertTrue(result["passed"], result["reasons"])
        self.assertFalse(mask[240, 30])
        cv2.rectangle(frame, (90, 245), (125, 280), color, -1)
        self.assertFalse(inspect_variants(frame, profile)[0]["passed"])

    def test_clipped_triangle_corner_uses_measured_sides(self):
        mask = np.zeros((60, 80), np.uint8)
        contour = np.array([[64, 5], [5, 10], [5, 14], [35, 38]], np.int32).reshape(-1, 1, 2)
        cv2.fillPoly(mask, [contour], 255)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        raw = contours[0]
        self.assertNotEqual(len(edges(raw)), 3)
        fitted = fit_edge_polygon(raw, 3)
        self.assertIsNotNone(fitted)
        self.assertEqual(len(fitted), 3)
        self.assertLess(abs(cv2.contourArea(fitted)/cv2.contourArea(raw)-1), .12)

    def test_deep_notch_and_wrong_vertex_geometry_are_not_repaired(self):
        notch = np.array([[0, 0], [100, 0], [100, 100], [60, 100], [60, 45], [40, 45], [40, 100], [0, 100]], np.float32).reshape(-1, 1, 2)
        square = np.array([[0, 0], [100, 0], [100, 100], [0, 100]], np.float32).reshape(-1, 1, 2)
        self.assertIsNone(fit_edge_polygon(notch, 4))
        self.assertIsNone(fit_edge_polygon(square, 3))

    def test_unavailable_angle_is_null_not_ninety_degrees(self):
        frame, polygons = scene()
        profile = create_variant_profile(frame, polygons, "A", [80, 10, 450, 445])
        color = tuple(map(int, frame[80, 150]))
        cv2.fillPoly(frame, [polygons[0]], (65, 65, 65))
        cv2.circle(frame, (155, 90), 25, color, -1)
        result, _ = inspect_variants(frame, profile)
        ear = result["parts"][0]
        self.assertIsNone(ear["metrics"]["angle_degrees"])
        self.assertIn("edge_geometry", ear["reasons"])
        self.assertFalse(result["passed"])
        self.assertTrue(any(r["error_degrees"] is None and not r["passed"] for r in result["relations"]))


if __name__ == "__main__":
    unittest.main()
