"""Uncached published content. A configured runtime never falls back to fixture files."""
import copy
import json
from pathlib import Path
BASE = Path(__file__).resolve().parents[1]

def configured():
    from django.conf import settings
    return settings.configured

def legacy():
    return json.loads((BASE / 'server/catalog.json').read_text())

def catalog(db=None):
    if not configured():
        return legacy()
    from backoffice.content.models import GameFamily, LevelDefinition, CareerOffer, PointReward, LevelVersion
    levels = LevelDefinition.objects.filter(status='published', family__active=True).select_related('family').order_by('family__position', 'level', 'id')
    tasks = []
    for level in levels:
        version = LevelVersion.objects.filter(level=level, version=level.published_version).first()
        if version:
            tasks.append(copy.deepcopy(version.public_snapshot))
    games = [{'id': f.pk, 'title': f.title, 'description': f.description, **({'previewSpriteId': f.preview_sprite_id} if f.preview_sprite_id else {})} for f in GameFamily.objects.filter(active=True).order_by('position', 'id')]
    offers = [{'id': o.pk, **{key: getattr(o, key) for key in ('title', 'direction', 'type', 'location', 'schedule', 'pay', 'description', 'tasks', 'requirements', 'demo')}, **({'deadline': o.deadline} if o.deadline else {})} for o in CareerOffer.objects.filter(published=True, archived=False)]
    rewards = [{'id': r.pk, **{key: getattr(r, key) for key in ('title', 'description', 'cost', 'stock', 'demo')}, 'remaining': r.stock} for r in PointReward.objects.filter(published=True, archived=False)]
    return {'tasks': tasks, 'games': games, 'offers': offers, 'rewards': rewards, 'events': []}

def item(db, group, item_id):
    return next((row for row in catalog(db).get(group, []) if row['id'] == item_id), None)

def task(db, task_id):
    return item(db, 'tasks', task_id)

def resolve_rule(task):
    if not configured():
        from .level_rules import default_level_rules
        return default_level_rules().resolve(task)
    from backoffice.content.models import LevelVersion, LevelDefinition
    level = LevelDefinition.objects.filter(pk=task['id'], status='published', family__active=True).first()
    if not level:
        return None
    version = task.get('contentVersion', level.published_version)
    snapshot = LevelVersion.objects.filter(level=level, version=version).first()
    return copy.deepcopy(snapshot.private_rule) if snapshot else None

def publicassets(db=None):
    if not configured():
        return json.loads((BASE / 'src/games/sprite-manifest.json').read_text())
    from backoffice.content.models import SpriteAsset
    return {'schemaVersion': 1, 'sprites': [{'id': s.pk, 'kind': s.kind, 'src': s.source_path or '/api/game-assets/' + s.pk + '/', 'width': s.width, 'height': s.height, 'pixelWidth': s.pixel_width, 'pixelHeight': s.pixel_height} for s in SpriteAsset.objects.filter(active=True)]}

def asset(asset_id):
    from backoffice.content.models import SpriteAsset
    obj = SpriteAsset.objects.filter(pk=asset_id, active=True).first()
    if not obj:
        return None
    if obj.source_path:
        path = (BASE / 'public' / obj.source_path.lstrip('/')).resolve()
        if not path.is_relative_to((BASE / 'public/assets/games-v5').resolve()):
            return None
        if not path.exists():
            path = (BASE / 'dist' / obj.source_path.lstrip('/')).resolve()
            if not path.is_relative_to((BASE / 'dist/assets/games-v5').resolve()):
                return None
        if not path.exists():
            return None
        content = path.read_bytes()
    else:
        content = bytes(obj.content)
    return {'content': content, 'mimeType': obj.mime_type, 'filename': obj.pk + '.' + {'image/png': 'png', 'image/jpeg': 'jpg', 'image/webp': 'webp', 'image/svg+xml': 'svg'}[obj.mime_type]}
