import unittest
import cv2
import numpy as np

from test_variants import scene
from qc_station.variants import create_variant_profile, inspect_variants, fit_edge_polygon, edges


class ContourRobustnessTests(unittest.TestCase):
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
