import copy
import hashlib
import io
import json
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max
from PIL import Image
from backoffice.core.models import Material, MaterialVersion, MaterialQuestion, MaterialMedia, utc_stamp
from server import learning
from server.errors import APIError
from .models import LevelDefinition, LevelVersion, SpriteAsset
from .validation import require, finite, validate_fixtures, validate_task

def audit(actor, action, obj, fields=None):
    if actor is not None:
        from backoffice.operations.services import audit as write
        write(actor, action, obj, fields=fields or {})

def media_validator(db, media_id, audience):
    asset = MaterialMedia.objects.filter(pk=media_id).first()
    if not asset or asset.audience not in ('all', audience):
        raise ValueError('Медиафайл недоступен выбранной аудитории.')

def material_value(body):
    try:
        value = learning._definition(body, media_validator, None)
        learning._canonical(body.get('id'), value)
    except APIError as error:
        raise ValidationError(error.message) from error
    for block in value['blocks']:
        if block['type'] in ('image', 'video'):
            media = MaterialMedia.objects.get(pk=block['mediaId'])
            require(media.mime_type.startswith(block['type'] + '/'), 'Тип медиа не совпадает с типом блока.')
    return value

@transaction.atomic
def save_material(instance, value, actor=None, expected=None):
    current = Material.objects.select_for_update().filter(pk=instance.pk).first()
    require(not current or not current.archived, 'Архивный материал нельзя изменять.')
    require(not current or expected is None or expected == current.version, 'Материал изменён в другой вкладке. Обновите страницу.')
    version = current.version + 1 if current else 1
    for name in ('title', 'description', 'category', 'audience'):
        setattr(instance, name, value[name])
    instance.published = int(value['published'])
    instance.demo = int(value['demo'])
    instance.blocks = json.dumps(value['blocks'], ensure_ascii=False)
    instance.points = value['quiz']['points'] if value['quiz'] else 0
    instance.version = version
    instance.updated_at = utc_stamp()
    instance.save()
    MaterialVersion.objects.create(material=instance, version=version, snapshot=json.dumps(value, ensure_ascii=False))
    for position, question in enumerate(value['quiz']['questions'] if value['quiz'] else []):
        MaterialQuestion.objects.create(material=instance, version=version, question_id=question['id'], position=position, text=question['text'], options=json.dumps(question['options'], ensure_ascii=False), correct_option_id=question['correctOptionId'], explanation=question['explanation'])
    audit(actor, 'material.version', instance, {'version': version, 'published': value['published'], 'audience': value['audience']})
    return instance

def image_upload(upload, maximum=10 * 1024 * 1024):
    require(0 < upload.size <= maximum, 'Файл должен быть не больше 10 МБ.')
    data = upload.read()
    try:
        with Image.open(io.BytesIO(data)) as image:
            require(image.format in ('PNG', 'JPEG', 'WEBP'), 'Разрешены PNG, JPEG и WebP.')
            width, height = image.size
            mime = {'PNG': 'image/png', 'JPEG': 'image/jpeg', 'WEBP': 'image/webp'}[image.format]
            require(width * height <= 32000000 and 0 < width <= 32768 and 0 < height <= 32768, 'Изображение слишком большое.')
            image.verify()
    except (OSError, Image.DecompressionBombError) as error:
        raise ValidationError('Повреждённое изображение.') from error
    return (data, mime, width, height)

def ensure_asset_mutable(asset, data=None, width=None, height=None, active=None):
    current = SpriteAsset.objects.filter(pk=asset.pk).first()
    if not current:
        return
    changed = data is not None and bytes(current.content) != data or (width is not None and current.width != width) or (height is not None and current.height != height) or (active is False)
    if changed:
        for version in LevelVersion.objects.iterator():
            p = version.public_snapshot.get('presentation', {})
            used = set(p.get('sprites', {}).values()) | {o.get('spriteId') for o in p.get('scene', {}).get('objects', [])}
            require(asset.pk not in used, 'Спрайт используется опубликованной версией. Загрузите новый ID вместо изменения существующего.')

def presentation(level):
    value = copy.deepcopy(level.presentation or {'schemaVersion': 1, 'sprites': {}})
    require(isinstance(value,dict),'Оформление должно содержать поля.')
    value.setdefault('schemaVersion', 1)
    value.setdefault('sprites', {})
    scene = value.setdefault('scene', {'width': 358, 'height': 441, 'objects': []})
    require(isinstance(scene,dict),'Сцена должна содержать поля.')
    scene.setdefault('objects', [])
    require(isinstance(scene['objects'],list) and all(isinstance(o,dict) for o in scene['objects']),'Проверьте объекты сцены.')
    validate_presentation(value)
    keys = {o.get('id') for o in scene['objects']}
    for instance in level.scene_objects.select_related('sprite', 'module').all():
        instance.full_clean()
        require(isinstance(instance.slot_values,dict),'Переопределения слотов должны быть словарём.')
        if instance.sprite:
            slots = [{'id': instance.key, 'spriteId': instance.sprite_id, 'x': 0, 'y': 0, 'width': instance.width, 'height': instance.height, 'rotation': 0, 'layer': 0, 'role': instance.binding}]
            sx = sy = 1
        else:
            require(instance.module.active, 'Модуль сцены выключен.')
            slots = instance.module.slots
            sx = instance.width / instance.module.width
            sy = instance.height / instance.module.height
            unknown = set(instance.slot_values) - {slot['id'] for slot in slots}
            require(not unknown, 'Неизвестный слот композиции.')
        for slot in slots:
            asset_id = instance.slot_values.get(slot['id'], slot['spriteId'])
            role = slot.get('role') or (instance.binding if instance.sprite else '')
            require(SpriteAsset.objects.filter(pk=asset_id, active=True).exists(), 'Спрайт слота отсутствует или выключен.')
            if role:
                value['sprites'][role] = asset_id
            else:
                key = instance.key + ':' + slot['id']
                require(key not in keys, 'Повтор ID объекта сцены.')
                keys.add(key)
                scene['objects'].append({'id': key, 'spriteId': asset_id, 'x': instance.x + slot.get('x', 0) * sx, 'y': instance.y + slot.get('y', 0) * sy, 'width': slot['width'] * sx, 'height': slot['height'] * sy, 'rotation': instance.rotation + slot.get('rotation', 0), 'layer': instance.layer + slot.get('layer', 0)})
    validate_presentation(value)
    return value

def validate_presentation(value):
    require(isinstance(value, dict) and value.get('schemaVersion') == 1 and isinstance(value.get('sprites'), dict), 'Некорректное оформление.')
    assets = set(SpriteAsset.objects.filter(active=True).values_list('id', flat=True))
    require(all((isinstance(role, str) and role.strip() and isinstance(asset,str) and (asset in assets) for role, asset in value['sprites'].items())), 'Неизвестный спрайт в роли.')
    if 'scene' in value:
        scene = value['scene']
        require(isinstance(scene, dict) and finite(scene.get('width')) and finite(scene.get('height')) and (1 <= scene['width'] <= 4096) and (1 <= scene['height'] <= 4096), 'Проверьте размеры сцены.')
        require(isinstance(scene.get('objects'), list) and len(scene['objects']) <= 200, 'До 200 объектов в сцене.')
        keys = set()
        for obj in scene['objects']:
            require(isinstance(obj, dict) and isinstance(obj.get('id'), str) and (obj['id'] not in keys) and isinstance(obj.get('spriteId'),str) and (obj.get('spriteId') in assets), 'Неизвестный или повторный объект сцены.')
            keys.add(obj['id'])
            require(all((finite(obj.get(k)) for k in ('x', 'y', 'width', 'height'))) and obj['width'] > 0 and (obj['height'] > 0), 'Некорректная геометрия.')
            require(0 <= obj['x'] < scene['width'] and 0 <= obj['y'] < scene['height'] and (obj['x'] + obj['width'] <= scene['width']) and (obj['y'] + obj['height'] <= scene['height']), 'Объект выходит за границы сцены.')
            require(finite(obj.get('rotation', 0)) and type(obj.get('layer', 0)) is int and (abs(obj.get('layer', 0)) <= 100), 'Некорректный поворот или слой.')

def task_snapshot(level):
    return {'id': level.pk, 'game': level.family_id, 'level': level.level, 'title': level.title, 'description': level.description, 'direction': level.direction, 'points': level.points, 'duration': level.duration, 'offerId': level.offer_id, 'demo': level.demo, 'explanation': level.explanation, **({'careerExplanation':level.career_explanation} if level.career_explanation else {}), 'puzzle': copy.deepcopy(level.puzzle), 'presentation': presentation(level)}

def check_level(level):
    task = task_snapshot(level)
    rule = copy.deepcopy(level.rule_set.definition) if level.rule_set_id else None
    require(not level.rule_set_id or level.rule_set.game == level.family_id, 'Механика приватного правила не совпадает с игрой.')
    report = validate_fixtures(task, level.fixtures, rule)
    return (task, rule, report)

@transaction.atomic
def publish_level(level, actor=None):
    locked = LevelDefinition.objects.select_for_update().get(pk=level.pk)
    task, rule, report = check_level(locked)
    version = (locked.versions.aggregate(value=Max('version'))['value'] or 0) + 1
    task['contentVersion'] = version
    LevelVersion.objects.create(level=locked, version=version, public_snapshot=task, private_rule=rule, fixtures=locked.fixtures)
    locked.status = 'published'
    locked.published_version = version
    locked.save(update_fields=['status', 'published_version', 'updated_at'])
    audit(actor, 'level.publish', locked, {'version': version, 'snapshotHash': hashlib.sha256(json.dumps(task, sort_keys=True).encode()).hexdigest()})
    return (locked, report)

@transaction.atomic
def save_reward(reward, actor=None):
    from server.postgres import connect
    from backoffice.core.models import RewardExchange
    connect().lock('reward', reward.pk)
    require(reward.stock >= RewardExchange.objects.filter(reward=reward.pk).count(), 'Остаток не может быть меньше числа уже оформленных обменов.')
    reward.full_clean()
    reward.save()
    audit(actor, 'reward.catalog_change', reward, ['cost', 'stock', 'published', 'archived'])
    return reward
