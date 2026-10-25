"""Explicit, conservative seed-copy update; bootstrap never overwrites editors."""
import copy
import json
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from backoffice.content.models import CareerOffer, LevelDefinition
from backoffice.content.seed import witness
from backoffice.content.services import check_level, publish_level
from backoffice.operations.models import OperationsAudit


LEVEL_FIELDS = {
    'id': 'pk', 'game': 'family_id', 'level': 'level', 'title': 'title',
    'description': 'description', 'direction': 'direction', 'points': 'points',
    'duration': 'duration', 'offerId': 'offer_id', 'demo': 'demo',
    'explanation': 'explanation', 'careerExplanation': 'career_explanation',
    'puzzle': 'puzzle', 'presentation': 'presentation',
}
LEVEL_COPY = {'title', 'description', 'duration', 'explanation', 'careerExplanation'}
OFFER_FIELDS = {
    key: key for key in ('id', 'title', 'direction', 'type', 'location', 'schedule',
                         'pay', 'description', 'tasks', 'requirements', 'demo', 'deadline')
}
OFFER_COPY = {'title', 'direction', 'type', 'location', 'schedule', 'pay',
              'description', 'tasks', 'requirements', 'deadline'}


def catalog(path):
    try:
        value = json.loads(Path(path).read_text(encoding='utf-8'))
        for group in ('tasks', 'offers'):
            rows = value[group]
            if not isinstance(rows, list) or any(not isinstance(row, dict) or not isinstance(row.get('id'), str) for row in rows):
                raise ValueError()
            if len({row['id'] for row in rows}) != len(rows):
                raise ValueError()
        return value
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise CommandError('Нужен корректный каталог с уникальными tasks/offers; значения не изменены.') from error


def value(row, key):
    if key in ('offerId', 'explanation', 'careerExplanation', 'deadline'):
        return row.get(key, '')
    if key == 'presentation':
        return row.get(key, {'schemaVersion': 1, 'sprites': {}})
    return row.get(key)


def changed_fields(old, new):
    return {key for key in set(old) | set(new) if value(old, key) != value(new, key)}


def matches(current, old, new, mapping, ignored=()):
    # A manually edited *unchanged* field is also a reason to skip the object.
    for key, attribute in mapping.items():
        if key in ignored:
            continue
        actual = getattr(current, attribute)
        if actual != value(old, key) and actual != value(new, key):
            return False
    return True


def record_audit(obj, fields):
    OperationsAudit.objects.create(
        actor=None, actor_name='system:sync_seed_copy', action='seed.copy_sync',
        entity=obj._meta.label_lower, entity_id=str(obj.pk),
        reason='Явное применение проверенных изменений стартовых текстов.',
        metadata={'fields': sorted(fields)},
    )


class Command(BaseCommand):
    help = 'Проверить изменения стартовых текстов без перезаписи ручных правок; применение только с --apply.'

    def add_arguments(self, parser):
        parser.add_argument('--baseline', required=True, help='Прежний server/catalog.json до изменения текстов.')
        parser.add_argument('--apply', action='store_true', help='Применить прошедшие проверки изменения; по умолчанию dry-run.')

    def handle(self, *args, **options):
        before = catalog(options['baseline'])
        after = catalog(Path(settings.BASE_DIR) / 'server' / 'catalog.json')
        try:
            rules = json.loads((Path(settings.BASE_DIR) / 'server' / 'level-rules.json').read_text())
        except (OSError, ValueError) as error:
            raise CommandError('Стартовые приватные определения не прочитаны; синхронизация отменена.') from error
        results = []
        for group, model, allowed in [('tasks', LevelDefinition, LEVEL_COPY), ('offers', CareerOffer, OFFER_COPY)]:
            previous = {row['id']: row for row in before[group]}
            for new in after[group]:
                old = previous.get(new['id'])
                if old is None:
                    continue  # This command never creates definitions.
                changed = changed_fields(old, new)
                if not changed:
                    continue
                result = {'kind': group, 'id': new['id'], 'fields': sorted(changed)}
                if not changed <= allowed:
                    result.update(status='skipped', reason='non_copy_change')
                    results.append(result)
                    continue
                try:
                    with transaction.atomic():
                        obj = model.objects.select_for_update().filter(pk=new['id']).first()
                        if obj is None:
                            status, reason = 'skipped', 'missing_definition'
                        elif group == 'tasks':
                            status, reason = self.level(obj, old, new, changed, rules, options['apply'])
                        else:
                            status, reason = self.offer(obj, old, new, changed, options['apply'])
                except ValidationError:
                    status, reason = 'skipped', 'validation_failed'
                result.update(status=status)
                if reason:
                    result['reason'] = reason
                results.append(result)
        summary = {'dryRun': not options['apply'],
                   **{status: sum(result['status'] == status for result in results)
                      for status in ('updated', 'would_update', 'unchanged', 'skipped')},
                   'results': results}
        self.stdout.write(json.dumps(summary, ensure_ascii=False))

    def level(self, obj, old, new, changed, rules, apply):
        # Seed levels were published. Draft/archive/inactive state is an editorial decision.
        if obj.status != 'published' or not obj.family.active:
            return 'skipped', 'editorial_state'
        if not matches(obj, old, new, LEVEL_FIELDS) or obj.scene_objects.exists():
            return 'skipped', 'manual_edit'
        rule_ref = rules['levels'].get(obj.pk)
        expected_rule = rules['rules'].get(rule_ref)
        if obj.rule_set_id != rule_ref or (obj.rule_set.definition if obj.rule_set_id else None) != expected_rule:
            return 'skipped', 'manual_rule'
        expected_fixtures = {'positive': [witness(old, expected_rule)], 'negative': [{}]}
        if obj.fixtures != expected_fixtures:
            return 'skipped', 'manual_fixtures'
        published = obj.versions.filter(version=obj.published_version).first()
        if published is None or published.private_rule != expected_rule or published.fixtures != expected_fixtures:
            return 'skipped', 'publication_mismatch'
        # Compiled presentation contains generated scene defaults; raw editable
        # presentation was compared above, so those derived keys are ignored here.
        for key in LEVEL_FIELDS:
            if key == 'presentation':
                continue
            actual = value(published.public_snapshot, key)
            if actual != value(old, key) and actual != value(new, key):
                return 'skipped', 'manual_publication'
        pending = {key for key in changed if getattr(obj, LEVEL_FIELDS[key]) != value(new, key)}
        if not pending:
            return 'unchanged', None
        for key in pending:
            setattr(obj, LEVEL_FIELDS[key], copy.deepcopy(value(new, key)))
        check_level(obj)  # The real positive/negative validators also run in dry-run.
        if not apply:
            return 'would_update', None
        obj.full_clean()
        obj.save(update_fields=[LEVEL_FIELDS[key] for key in pending] + ['updated_at'])
        publish_level(obj, actor=None)
        record_audit(obj, pending)
        return 'updated', None

    def offer(self, obj, old, new, changed, apply):
        if obj.archived or not obj.published:
            return 'skipped', 'editorial_state'
        if not matches(obj, old, new, OFFER_FIELDS):
            return 'skipped', 'manual_edit'
        pending = {key for key in changed if getattr(obj, OFFER_FIELDS[key]) != value(new, key)}
        if not pending:
            return 'unchanged', None
        for key in pending:
            setattr(obj, OFFER_FIELDS[key], copy.deepcopy(value(new, key)))
        obj.full_clean()
        if not apply:
            return 'would_update', None
        obj.save(update_fields=[OFFER_FIELDS[key] for key in pending])
        record_audit(obj, pending)
        return 'updated', None
