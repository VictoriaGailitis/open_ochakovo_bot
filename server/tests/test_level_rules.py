"""Declarative private rules allow new level IDs without changing validators."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from server.app import CATALOG
from server.level_rules import LevelRuleError, LevelRuleRegistry, load_level_rules
from server.shift import assess, completion_details
from server.solutions import validate


def definitions():
    return {
        'schemaVersion': 1,
        'levels': {'new-history': 'new-history-rule-v1', 'new-shift': 'new-shift-rule-v1'},
        'rules': {
            'new-history-rule-v1': {'game': 'history', 'answers': {'new-question': 'option-b'}},
            'new-shift-rule-v1': {
                'game': 'shift',
                'observedChange': 'new-location', 'explanation': 'new-cause',
                'nextStep': 'new-safe-action', 'responsible': 'new-owner',
                'localizationPaths': [[['new-flow']], [['new-upstream'], ['new-downstream']]],
                'causeFacts': ['new-check', 'new-journal'], 'contradictoryFacts': ['new-rumor'],
                'explanationText': 'Configured assessment text.',
                'outcome': {'summary': 'Configured outcome.', 'before': 'Before.', 'after': 'After.'},
                'assessment': {'localization': 10, 'cause': 10, 'nextStep': 10},
            },
        },
    }


def history_task():
    return {'id': 'new-history', 'game': 'history', 'puzzle': {'questions': [
        {'id': 'new-question', 'text': 'New question', 'source': 'Source',
         'options': [{'id': 'option-a', 'text': 'A'}, {'id': 'option-b', 'text': 'B'}]},
    ]}}


def shift_task():
    rule = definitions()['rules']['new-shift-rule-v1']
    return {'id': 'new-shift', 'game': 'shift', 'puzzle': {
        'facts': [{'id': fact, 'source': 'Source', 'time': '12:00:00', 'text': fact}
                  for fact in ['new-flow', 'new-upstream', 'new-downstream', 'new-check', 'new-journal', 'new-rumor']],
        'conclusion': {key: [{'id': rule[key], 'label': key}, {'id': 'other', 'label': 'Other'}]
                       for key in ['observedChange', 'explanation', 'nextStep', 'responsible']},
    }}


def shift_solution(evidence=None):
    rule = definitions()['rules']['new-shift-rule-v1']
    return {**{key: rule[key] for key in ['observedChange', 'explanation', 'nextStep', 'responsible']},
            'evidence': evidence if evidence is not None else ['new-flow', 'new-check']}


class LevelRulesTest(unittest.TestCase):
    def test_new_history_id_and_question_answer_ids_are_defined_only_by_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'rules.json'
            path.write_text(json.dumps(definitions()))
            registry = load_level_rules(path)
        self.assertEqual(validate(history_task(), {'answers': {'new-question': 'option-b'}}, registry), [])
        self.assertTrue(validate(history_task(), {'answers': {'new-question': 'option-a'}}, registry))
        self.assertTrue(validate(history_task(), {'answers': {}}, registry))

    def test_new_shift_id_uses_configured_claims_paths_and_result(self):
        registry = LevelRuleRegistry(definitions())
        task = shift_task()
        for evidence in [['new-flow', 'new-check'], ['new-upstream', 'new-downstream', 'new-journal']]:
            self.assertEqual(assess(task, shift_solution(evidence), evidence, registry), [])
            self.assertEqual(validate(task, shift_solution(evidence), registry), [])
        self.assertTrue(assess(task, shift_solution(), ['new-flow'], registry))
        self.assertTrue(assess(task, shift_solution(['new-flow']), registry=registry))
        self.assertTrue(assess(task, shift_solution(['new-flow', 'new-check', 'new-rumor']), registry=registry))
        self.assertTrue(assess(task, {**shift_solution(), 'nextStep': 'unsafe'}, registry=registry))
        details = completion_details(task, registry)
        self.assertEqual(details['explanation'], 'Configured assessment text.')
        self.assertEqual(details['outcome']['after'], 'After.')
        self.assertEqual(details['assessment'], {'localization': 10, 'cause': 10, 'nextStep': 10})

    def test_missing_or_wrong_game_mapping_rejects_even_an_otherwise_correct_solution(self):
        registry = LevelRuleRegistry(definitions())
        self.assertTrue(validate({**history_task(), 'id': 'unconfigured'}, {'answers': {'new-question': 'option-b'}}, registry))
        self.assertTrue(assess({**shift_task(), 'id': 'unconfigured'}, shift_solution(), registry=registry))
        self.assertTrue(validate({**history_task(), 'id': 'new-shift'}, {'answers': {'new-question': 'option-b'}}, registry))
        with self.assertRaises(ValueError):
            completion_details({**shift_task(), 'id': 'unconfigured'}, registry)

    def test_invalid_configuration_cannot_create_vacuously_successful_paths(self):
        variants = []
        for key, value in [('localizationPaths', []), ('localizationPaths', [[]]),
                           ('localizationPaths', [[[]]]), ('causeFacts', []),
                           ('causeFacts', 'new-check'), ('explanation', ''),
                           ('assessment', {'localization': True, 'cause': 10, 'nextStep': 10})]:
            document = definitions()
            document['rules']['new-shift-rule-v1'][key] = value
            variants.append(document)
        unknown = definitions()
        unknown['levels']['new-history'] = 'missing-rule'
        variants.extend([unknown, {**definitions(), 'schemaVersion': 2}])
        for document in variants:
            with self.subTest(document=document):
                with self.assertRaises(LevelRuleError):
                    LevelRuleRegistry(document)

    def test_rules_with_missing_public_references_or_duplicate_ids_fail_closed(self):
        registry = LevelRuleRegistry(definitions())
        history = history_task()
        history['puzzle']['questions'][0]['options'].pop()
        self.assertTrue(validate(history, {'answers': {'new-question': 'option-b'}}, registry))
        history = history_task()
        history['puzzle']['questions'].append(copy.deepcopy(history['puzzle']['questions'][0]))
        self.assertTrue(validate(history, {'answers': {'new-question': 'option-b'}}, registry))
        shift = shift_task()
        shift['puzzle']['facts'] = [fact for fact in shift['puzzle']['facts'] if fact['id'] != 'new-check']
        self.assertTrue(assess(shift, shift_solution(), registry=registry))
        shift = shift_task()
        shift['puzzle']['conclusion']['responsible'].pop(0)
        self.assertTrue(assess(shift, shift_solution(), registry=registry))

    def test_missing_corrupt_and_duplicate_key_files_fail_closed_without_default_answers(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'rules.json'
            with self.assertRaises(LevelRuleError):
                load_level_rules(path)
            for text in ['{bad json', '{"schemaVersion":1,"schemaVersion":1,"levels":{},"rules":{}}']:
                path.write_text(text)
                with self.assertRaises(LevelRuleError):
                    load_level_rules(path)
        with patch('server.level_rules.default_level_rules', side_effect=LevelRuleError('Unavailable')):
            self.assertTrue(validate(history_task(), {'answers': {'new-question': 'option-b'}}))
            self.assertTrue(assess(shift_task(), shift_solution()))
            with self.assertRaises(ValueError):
                completion_details(shift_task())

    def test_resolved_definitions_are_isolated_and_private_rules_do_not_enter_catalog(self):
        registry = LevelRuleRegistry(definitions())
        resolved = registry.resolve(history_task())
        resolved['answers']['new-question'] = 'option-a'
        self.assertEqual(validate(history_task(), {'answers': {'new-question': 'option-b'}}, registry), [])
        public = json.dumps(CATALOG)
        for private_key in ['localizationPaths', 'causeFacts', 'contradictoryFacts', 'explanationText', 'assessment']:
            self.assertNotIn('"' + private_key + '"', public)
        production = load_level_rules()
        for task in CATALOG['tasks']:
            if task['game'] in ('history', 'shift'):
                self.assertIsNotNone(production.resolve(task), task['id'])


if __name__ == '__main__':
    unittest.main()
