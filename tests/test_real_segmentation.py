"""Reproduce illumination fragmentation from the user's actual camera capture."""
import json
from pathlib import Path
import unittest

import cv2

from qc_station.variants import inspect_variants
from qc_station.acceptance import accept_five_parts


class RealSegmentationTests(unittest.TestCase):
    def test_fragmented_blue_surfaces_are_seven_parts_without_forcing_pass(self):
        folder = Path(__file__).parent / 'fixtures' / 'segmentation_20260925'
        profile = json.loads((folder/'profile.json').read_text())
        frame = cv2.imread(str(folder/'frame.png'))
        result, _ = inspect_variants(frame, profile)
        self.assertEqual(result['found_count'], 7)
        self.assertEqual(result['detected_variant'], 'A')
        self.assertNotIn('part_count', result['reasons'])
        for name in ('body', 'foot', 'left_ear'):
            part = next(p for p in result['parts'] if p['name'] == name)
            self.assertTrue(part['passed'], part)
        # The yellow ear still has a measured notch; color recovery must not
        # replace that boundary with an ideal triangle to manufacture PASS.
        ear = next(p for p in result['parts'] if p['name'] == 'right_ear')
        self.assertIn('edge_geometry', ear['reasons'])
        self.assertFalse(result['passed'])
        accepted = accept_five_parts(result, profile)
        self.assertTrue(accepted['passed'])
        self.assertFalse(accepted['strict_passed'])

    def test_missing_blue_piece_is_not_reconstructed_from_template(self):
        folder = Path(__file__).parent / 'fixtures' / 'segmentation_20260925'
        profile = json.loads((folder/'profile.json').read_text())
        frame = cv2.imread(str(folder/'frame.png'))
        cv2.rectangle(frame, (345, 15), (521, 85), (100, 100, 100), -1)
        result, _ = inspect_variants(frame, profile)
        self.assertFalse(result['passed'])
        foot = next(p for p in result['parts'] if p['name'] == 'foot')
        self.assertFalse(foot['passed'])
