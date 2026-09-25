import copy
import unittest

from qc_station.acceptance import accept_five_parts
from qc_station.variants import PART_NAMES, VARIANTS


class AcceptanceTests(unittest.TestCase):
    def result(self, names=PART_NAMES, expected='A'):
        colors = dict(zip(PART_NAMES, VARIANTS['A']))
        return {'passed': False, 'found_count': len(names), 'expected_variant': expected,
                'reasons': ['edge_relations'], 'parts': [
                    {'name': n, 'color': colors[n], 'color_fractions': {colors[n]: 1},
                     'reasons': ['edge_geometry']} for n in names]}

    def apply(self, result):
        return accept_five_parts(result, {'schema_version': 2,
                                         'thresholds': {'color_fraction': .65}})

    def test_five_recognized_parts_pass_despite_geometry(self):
        result = self.apply(self.result(PART_NAMES[:5]))
        self.assertTrue(result['passed'])
        self.assertFalse(result['strict_passed'])
        self.assertEqual(result['detected_variant'], 'A')
        self.assertEqual(result['reasons'], ['edge_relations'])

    def test_four_parts_cannot_pass(self):
        self.assertFalse(self.apply(self.result(PART_NAMES[:4]))['passed'])

    def test_wrong_order_variant_cannot_pass(self):
        self.assertFalse(self.apply(self.result(expected='B'))['passed'])

    def test_missing_ears_leave_variant_ambiguous(self):
        self.assertFalse(self.apply(self.result(PART_NAMES[2:]))['passed'])

    def test_seven_parts_with_geometry_errors_pass(self):
        original = self.result()
        result = self.apply(copy.deepcopy(original))
        self.assertTrue(result['passed'])
        self.assertEqual(result['parts'], original['parts'])
