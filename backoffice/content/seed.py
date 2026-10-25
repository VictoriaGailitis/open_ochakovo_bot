"""Idempotent initial content import. Never overwrites an editor's work."""
import copy
import hashlib
import itertools
import json
from pathlib import Path
from django.db import transaction
from server.solutions import validate
from .models import *
from .services import publish_level, save_material, material_value
from backoffice.core.models import Material
BASE = Path(__file__).resolve().parents[2]

def witness(task, rule=None):
    p = task['puzzle']
    game = task['game']
    if game == 'signal':
        return {'rules': [{'condition': {'color': 'red', 'mark': 'marked', 'combined': 'red_marked'}[p['rule']], 'output': 'left'}, {'condition': 'always', 'output': 'right'}]}
    if game == 'history':
        return {'answers': copy.deepcopy(rule['answers'])}
    if game == 'shift':
        return {**{key: rule[key] for key in ('observedChange', 'explanation', 'nextStep', 'responsible')}, 'evidence': list(dict.fromkeys([category[0] for category in rule['localizationPaths'][0]] + [rule['causeFacts'][0]]))}
    if game == 'lab':
        sample = next((s for s in p['samples'] if s['properties'] == p['observations']))
        return {'sampleId': sample['id'], 'evidence': [test['id'] for test in p['tests']]}
    if game == 'movement':
        source = (p['source']['x'], p['source']['y'])
        target = (p['target']['x'], p['target']['y'])

        def walk(path):
            current = path[-1]
            if current == target:
                value = {'gears': [{'x': x, 'y': y} for x, y in path[1:-1]], 'belts': []}
                return value if not validate(task, value) else None
            if len(path) > p['maxGears'] + 1:
                return None
            for dx, dy in ((1, 0), (0, 1), (-1, 0), (0, -1)):
                cell = (current[0] + dx, current[1] + dy)
                if 0 <= cell[0] < p['width'] and 0 <= cell[1] < p['height'] and (cell not in path):
                    result = walk(path + [cell])
                    if result:
                        return result
        result = walk([source])
        if result:
            return result
    if game == 'delivery':
        selected = []
        for order in p['order']:
            selected.extend([b for b in p['batches'] if b['product'] == order['product'] and (not b['reserved'])][:order['quantity']])

        def pack(index, occupied, placements):
            if index == len(selected):
                return placements
            batch = selected[index]
            for rotated in (False, True):
                for y in range(p['height']):
                    for x in range(p['width']):
                        cells = {(x + (dy if rotated else dx), y + (dx if rotated else dy)) for dx, dy in batch['cells']}
                        if not cells & occupied and all((0 <= a < p['width'] and 0 <= b < p['height'] for a, b in cells)):
                            found = pack(index + 1, occupied | cells, placements + [{'batchId': batch['id'], 'x': x, 'y': y, 'rotated': rotated}])
                            if found is not None:
                                return found
        placements = pack(0, set(), [])
        route = [dict(p['start'])]
        for batch in selected:
            for axis in ('x', 'y'):
                while route[-1][axis] != batch['location'][axis]:
                    new = dict(route[-1])
                    new[axis] += 1 if new[axis] < batch['location'][axis] else -1
                    route.append(new)
        result = {'placements': placements, 'route': route}
        if not validate(task, result):
            return result
    raise ValueError('Initial level has no valid witness: ' + task['id'])

@transaction.atomic
def seed_content():
    catalog = json.loads((BASE / 'server/catalog.json').read_text())
    rules = json.loads((BASE / 'server/level-rules.json').read_text())
    manifest = json.loads((BASE / 'src/games/sprite-manifest.json').read_text())
    for asset in manifest['sprites']:
        path = BASE / 'public' / asset['src'].lstrip('/')
        data = path.read_bytes()
        obj, _ = SpriteAsset.objects.get_or_create(id=asset['id'], defaults={'title': asset['id'], 'kind': asset['kind'], 'width': asset['width'], 'height': asset['height'], 'pixel_width': asset['pixelWidth'], 'pixel_height': asset['pixelHeight'], 'mime_type': 'image/svg+xml' if path.suffix == '.svg' else 'image/png', 'source_path': asset['src'], 'digest': hashlib.sha256(data).hexdigest()})
        SpriteModule.objects.get_or_create(id=asset['id'] + '-module', defaults={'title': asset['id'], 'kind': asset['kind'], 'width': asset['width'], 'height': asset['height'], 'slots': [{'id': 'main', 'label': 'Основной', 'spriteId': asset['id'], 'x': 0, 'y': 0, 'width': asset['width'], 'height': asset['height']}]})
    for position, game in enumerate(catalog['games']):
        GameFamily.objects.get_or_create(id=game['id'], defaults={'title': game['title'], 'description': game['description'], 'position': position, 'preview_sprite_id': game.get('previewSpriteId')})
    for key, rule in rules['rules'].items():
        RuleSet.objects.get_or_create(id=key, defaults={'title': key, 'game': rule['game'], 'definition': rule})
    for task in catalog['tasks']:
        if LevelDefinition.objects.filter(pk=task['id']).exists():
            continue
        rule_ref = rules['levels'].get(task['id'])
        rule = rules['rules'].get(rule_ref)
        value = {name: task[name] for name in ('level', 'title', 'description', 'direction', 'points', 'duration', 'demo', 'explanation', 'puzzle')}
        value.update(family_id=task['game'], offer_id=task.get('offerId', ''), presentation=task.get('presentation', {'schemaVersion': 1, 'sprites': {}}), rule_set_id=rule_ref, fixtures={'positive': [witness(task, rule)], 'negative': [{}]})
        obj = LevelDefinition.objects.create(id=task['id'], **value)
        publish_level(obj)
    for row in catalog['offers']:
        CareerOffer.objects.get_or_create(id=row['id'], defaults={**{k: v for k, v in row.items() if k != 'id'}, 'published': True})
    for row in catalog['rewards']:
        PointReward.objects.get_or_create(id=row['id'], defaults={**{k: v for k, v in row.items() if k not in ('id', 'remaining')}, 'published': True})
    for body in json.loads((BASE / 'server/learning-seed.json').read_text())['materials']:
        if not Material.objects.filter(pk=body['id']).exists():
            save_material(Material(id=body['id']), material_value(body))
    return {'families': GameFamily.objects.count(), 'levels': LevelDefinition.objects.count(), 'assets': SpriteAsset.objects.count(), 'materials': Material.objects.count()}
