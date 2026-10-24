"""Signed gear/belt networks validate actual topology, not a UI success flag."""
import copy
import unittest
from server.solutions import validate_movement


def point(x, y=1):
    return {'x': x, 'y': y}


def link(a, b):
    return {'from': point(a), 'to': point(b)}


def puzzle():
    return {'width': 5, 'height': 3, 'source': {**point(0), 'direction': 1},
            'target': {**point(4), 'direction': 1}, 'maxGears': 5,
            'maxBelts': 2, 'beltLinks': [link(0, 2), link(0, 3), link(1, 3), link(0, 4)]}


class MovementNetworkTests(unittest.TestCase):
    def test_legacy_gears_flip_and_missing_belts_remains_compatible(self):
        p = puzzle(); p.pop('maxBelts'); p.pop('beltLinks')
        self.assertEqual(validate_movement(p, {'gears': [point(1), point(2), point(3)]}), [])
        self.assertTrue(validate_movement(p, {'gears': []}))
        self.assertTrue(validate_movement(p, {'gears': [point(1), point(3)]}))
        self.assertTrue(validate_movement(p, {'gears': [point(1)], 'belts': [link(0, 4)]}))

    def test_open_belt_preserves_rotation_across_a_gap_and_accepts_reversed_pair(self):
        p = puzzle()
        for belt in [link(0, 2), link(2, 0)]:
            with self.subTest(belt=belt):
                self.assertEqual(validate_movement(p, {'gears': [point(2), point(3)], 'belts': [belt]}), [])
        p['target']['direction'] = -1
        self.assertTrue(validate_movement(p, {'gears': [point(2), point(3)], 'belts': [link(0, 2)]}))

    def test_belt_can_connect_fixed_shafts_without_any_added_gears(self):
        self.assertEqual(validate_movement(puzzle(), {'gears': [], 'belts': [link(0, 4)]}), [])

    def test_signed_cycles_reject_conflicting_and_allow_consistent_constraint(self):
        gears = [point(1), point(2), point(3)]
        consistent = {'gears': gears, 'belts': [link(0, 2)]}
        conflicting = {'gears': gears, 'belts': [link(0, 3)]}
        self.assertEqual(validate_movement(puzzle(), consistent), [])
        self.assertIn('заблокирован', validate_movement(puzzle(), conflicting)[0])
        p = puzzle(); p['beltLinks'].append(link(0, 1))
        self.assertIn('заблокирован', validate_movement(p, {'gears': gears, 'belts': [link(0, 1)]})[0])

    def test_duplicate_reversed_links_unknown_shafts_limits_and_detached_parts(self):
        p = puzzle()
        cases = [
            {'gears': [], 'belts': [link(0, 4), link(4, 0)]},
            {'gears': [point(3)], 'belts': [link(0, 2)]},
            {'gears': [point(1), point(3)], 'belts': [link(0, 3), link(1, 3), link(0, 4)]},
            {'gears': [point(1)], 'belts': [link(1, 4)]},
            {'gears': [point(1), point(1)], 'belts': [link(0, 4)]},
            {'gears': [point(2, 0)], 'belts': [link(0, 4)]},
        ]
        for solution in cases:
            with self.subTest(solution=solution):
                self.assertTrue(validate_movement(p, solution))
        for missing in ['maxBelts', 'beltLinks']:
            disabled = copy.deepcopy(p); disabled.pop(missing)
            self.assertTrue(validate_movement(disabled, {'gears': [], 'belts': [link(0, 4)]}))

    def test_malformed_coordinates_and_unknown_fields_are_not_ignored(self):
        invalid = [None, {}, {'from': point(0), 'to': point(0)},
                   {'from': point(-1), 'to': point(4)},
                   {'from': point(0), 'to': point(5)},
                   {'from': point(0), 'to': point(4, 3)},
                   {'from': point(False), 'to': point(4)},
                   {'from': point(0), 'to': point(4.0)},
                   {'from': point('0'), 'to': point(4)},
                   {'from': {**point(0), 'extra': 1}, 'to': point(4)},
                   {**link(0, 4), 'crossed': True}]
        for belt in invalid:
            with self.subTest(belt=belt):
                self.assertTrue(validate_movement(puzzle(), {'gears': [], 'belts': [belt]}))
        for belts in [None, {}, '0,1:4,1']:
            self.assertTrue(validate_movement(puzzle(), {'gears': [point(1)], 'belts': belts}))

    def test_current_levels_keep_gear_solution_and_support_a_real_bridge(self):
        import json
        from pathlib import Path
        catalog = json.loads(Path('server/catalog.json').read_text())
        for task in [t for t in catalog['tasks'] if t['game'] == 'movement']:
            p = task['puzzle']; target = p['target']
            gears = [point(x) for x in range(1, target['x'] + 1)]
            if target['y'] == 1:
                gears.pop()
            self.assertEqual(validate_movement(p, {'gears': gears}), [], task['id'])
            # A two-cell bridge replaces the intermediate wheel and has the same parity.
            bridge = next(link for link in p['beltLinks'] if link['from'] == point(0) and link['to'] == point(2))
            left, right = bridge['from'], bridge['to']
            middle = {'x': (left['x'] + right['x']) // 2, 'y': (left['y'] + right['y']) // 2}
            self.assertEqual(validate_movement(p, {'gears': [g for g in gears if g != middle], 'belts': [bridge]}), [], task['id'])


if __name__ == '__main__':
    unittest.main()
