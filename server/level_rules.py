"""Private, declarative assessment definitions; never part of the public catalog.

The levels map binds a stable task ID to a reusable rule reference. A reference
is resolved only when its game and all puzzle entity references still match.
There is no expression evaluator or client-controlled rule selection.
"""
import copy
import json
from functools import lru_cache
from pathlib import Path


RULES_PATH = Path(__file__).with_name('level-rules.json')
CLAIMS = ('observedChange', 'explanation', 'nextStep', 'responsible')
ASSESSMENT = ('localization', 'cause', 'nextStep')


class LevelRuleError(ValueError):
    """Invalid private configuration; callers must never accept a fallback."""


def _require(condition):
    if not condition:
        raise LevelRuleError('Invalid private level rule configuration.')


def _string(value):
    return isinstance(value, str) and bool(value.strip())


def _strings(value, allow_empty=False):
    return (isinstance(value, list) and (allow_empty or bool(value))
            and all(_string(item) for item in value)
            and len(value) == len(set(value)))


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result)
        result[key] = value
    return result


def _validate_rule(rule):
    _require(isinstance(rule, dict))
    if rule.get('game') == 'history':
        _require(set(rule) == {'game', 'answers'})
        answers = rule['answers']
        _require(isinstance(answers, dict) and bool(answers))
        _require(all(_string(k) and _string(v) for k, v in answers.items()))
        return
    _require(rule.get('game') == 'shift')
    _require(set(rule) == {'game', *CLAIMS, 'localizationPaths', 'causeFacts',
                           'contradictoryFacts', 'explanationText', 'outcome', 'assessment'})
    _require(all(_string(rule[key]) for key in (*CLAIMS, 'explanationText')))
    paths = rule['localizationPaths']
    _require(isinstance(paths, list) and bool(paths))
    for path in paths:
        _require(isinstance(path, list) and bool(path))
        _require(all(_strings(category) for category in path))
    _require(_strings(rule['causeFacts']))
    _require(_strings(rule['contradictoryFacts'], allow_empty=True))
    _require(not set(rule['causeFacts']) & set(rule['contradictoryFacts']))
    outcome = rule['outcome']
    _require(isinstance(outcome, dict) and set(outcome) == {'summary', 'before', 'after'})
    _require(all(_string(value) for value in outcome.values()))
    assessment = rule['assessment']
    _require(isinstance(assessment, dict) and set(assessment) == set(ASSESSMENT))
    _require(all(type(value) is int and 0 <= value <= 1000 for value in assessment.values()))


class LevelRuleRegistry:
    def __init__(self, document):
        _require(isinstance(document, dict) and set(document) == {'schemaVersion', 'levels', 'rules'})
        _require(type(document['schemaVersion']) is int and document['schemaVersion'] == 1)
        levels, rules = document['levels'], document['rules']
        _require(isinstance(levels, dict) and isinstance(rules, dict))
        _require(all(_string(k) and _string(v) for k, v in levels.items()))
        _require(all(_string(ref) for ref in rules))
        _require(all(ref in rules for ref in levels.values()))
        for rule in rules.values():
            _validate_rule(rule)
        self._levels = copy.deepcopy(levels)
        self._rules = copy.deepcopy(rules)

    def resolve(self, task):
        """Return an isolated definition only if every referenced public ID exists."""
        if not isinstance(task, dict):
            return None
        ref = self._levels.get(task.get('id'))
        rule = self._rules.get(ref)
        if not rule or rule['game'] != task.get('game'):
            return None
        try:
            puzzle = task['puzzle']
            if rule['game'] == 'history':
                questions = puzzle['questions']
                ids = [question['id'] for question in questions]
                if len(ids) != len(set(ids)) or set(ids) != set(rule['answers']):
                    return None
                for question in questions:
                    options = [option['id'] for option in question['options']]
                    if len(options) != len(set(options)) or rule['answers'][question['id']] not in options:
                        return None
            else:
                facts = [fact['id'] for fact in puzzle['facts']]
                if len(facts) != len(set(facts)):
                    return None
                referenced = set(rule['causeFacts']) | set(rule['contradictoryFacts'])
                referenced.update(fact for path in rule['localizationPaths'] for category in path for fact in category)
                if not referenced <= set(facts):
                    return None
                for claim in CLAIMS:
                    options = [option['id'] for option in puzzle['conclusion'][claim]]
                    if len(options) != len(set(options)) or rule[claim] not in options:
                        return None
            return copy.deepcopy(rule)
        except (KeyError, TypeError, ValueError):
            return None


def load_level_rules(path=RULES_PATH):
    try:
        document = json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=_unique_object)
    except (OSError, ValueError, TypeError) as error:
        raise LevelRuleError('Private level rules could not be loaded.') from error
    return LevelRuleRegistry(document)


@lru_cache(maxsize=1)
def default_level_rules():
    return load_level_rules()


def resolve_level_rule(task, registry=None):
    try:
        source = registry if registry is not None else default_level_rules()
        return source.resolve(task)
    except (LevelRuleError, KeyError, TypeError, ValueError, AttributeError):
        return None
