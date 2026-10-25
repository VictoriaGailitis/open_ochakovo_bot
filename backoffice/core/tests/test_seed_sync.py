"""Explicit copy-sync safety on PostgreSQL; no live database or Git access."""
import copy
import io
import json
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase

from backoffice.content.models import CareerOffer, LevelDefinition, LevelVersion
from backoffice.content.seed import seed_content
from backoffice.content.services import publish_level
from backoffice.core.models import GameProgress, LedgerEntry, MiniUser
from backoffice.operations.models import OperationsAudit


class SeedCopySyncTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_content()
        cls.current_catalog = json.loads((Path(settings.BASE_DIR) / 'server' / 'catalog.json').read_text())
        cls.baseline = copy.deepcopy(cls.current_catalog)
        for task in cls.baseline['tasks']:
            if task['id'] == 'signal-1':
                task['explanation'] = 'Прежнее объяснение учебного сигнала.'
            if task['id'] == 'shift-1':
                task.pop('careerExplanation', None)
        for offer in cls.baseline['offers']:
            if offer['id'] == 'lab':
                offer['title'] = 'Прежнее название практики'
                offer.pop('deadline', None)
        for key, field, old in [('signal-1', 'explanation', 'Прежнее объяснение учебного сигнала.'),
                                ('shift-1', 'career_explanation', '')]:
            level = LevelDefinition.objects.get(pk=key)
            setattr(level, field, old)
            level.save()
            publish_level(level)
        CareerOffer.objects.filter(pk='lab').update(title='Прежнее название практики', deadline='')
        user = MiniUser.objects.create(id='fixture:seed-sync')
        LedgerEntry.objects.create(id='fixture-seed-award', user=user, reason='task:signal-1', delta=50)
        GameProgress.objects.create(user=user, task='signal-1', draft='{"fixture":true}', completed='2026-10-25T00:00:00Z', draft_revision=123)

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.baseline_path = Path(self.directory.name) / 'baseline.json'
        self.baseline_path.write_text(json.dumps(self.baseline), encoding='utf-8')

    def sync(self, apply=False):
        output = io.StringIO()
        call_command('sync_seed_copy', baseline=str(self.baseline_path), apply=apply, stdout=output)
        return json.loads(output.getvalue())

    def test_default_dry_run_validates_but_does_not_publish_save_or_audit(self):
        versions = LevelVersion.objects.count()
        result = self.sync()
        self.assertTrue(result['dryRun'])
        self.assertEqual(result['would_update'], 3)
        self.assertEqual(result['updated'], 0)
        self.assertEqual(LevelVersion.objects.count(), versions)
        self.assertEqual(OperationsAudit.objects.filter(action='seed.copy_sync').count(), 0)
        self.assertEqual(LevelDefinition.objects.get(pk='signal-1').explanation, 'Прежнее объяснение учебного сигнала.')
        self.assertEqual(CareerOffer.objects.get(pk='lab').deadline, '')

    def test_apply_creates_new_immutable_versions_and_preserves_awards_and_progress(self):
        level = LevelDefinition.objects.get(pk='signal-1')
        old = level.versions.get(version=level.published_version)
        old_snapshot = copy.deepcopy(old.public_snapshot)
        count = LevelVersion.objects.count()
        ledger = list(LedgerEntry.objects.values())
        progress = list(GameProgress.objects.values())
        result = self.sync(apply=True)
        self.assertEqual(result['updated'], 3)
        self.assertEqual(result['skipped'], 0)
        self.assertEqual(LevelVersion.objects.count(), count + 2)
        old.refresh_from_db()
        self.assertEqual(old.public_snapshot, old_snapshot)
        level.refresh_from_db()
        latest = level.versions.get(version=level.published_version)
        expected = next(task for task in self.current_catalog['tasks'] if task['id'] == 'signal-1')
        self.assertEqual(latest.public_snapshot['explanation'], expected['explanation'])
        shift = LevelDefinition.objects.get(pk='shift-1')
        self.assertTrue(shift.versions.get(version=shift.published_version).public_snapshot['careerExplanation'])
        offer = CareerOffer.objects.get(pk='lab')
        expected_offer = next(row for row in self.current_catalog['offers'] if row['id'] == 'lab')
        self.assertEqual(offer.title, expected_offer['title'])
        self.assertEqual(offer.deadline, expected_offer['deadline'])
        self.assertGreater(len(offer.deadline), 40)
        self.assertEqual(list(LedgerEntry.objects.values()), ledger)
        self.assertEqual(list(GameProgress.objects.values()), progress)
        records = OperationsAudit.objects.filter(action='seed.copy_sync')
        self.assertEqual(records.count(), 3)
        self.assertFalse(records.exclude(actor=None).exists())
        self.assertEqual(set(records.values_list('actor_name', flat=True)), {'system:sync_seed_copy'})
        self.assertNotIn(expected['explanation'], json.dumps([record.metadata for record in records]))

    def test_second_apply_is_idempotent_without_new_versions_or_audit(self):
        self.sync(apply=True)
        count = LevelVersion.objects.count()
        records = OperationsAudit.objects.count()
        second = self.sync(apply=True)
        self.assertEqual(second['updated'], 0)
        self.assertEqual(second['unchanged'], 3)
        self.assertEqual(LevelVersion.objects.count(), count)
        self.assertEqual(OperationsAudit.objects.count(), records)

    def test_manual_copy_or_unchanged_field_edits_skip_entire_objects(self):
        level = LevelDefinition.objects.get(pk='signal-1')
        before = level.versions.count()
        level.description = 'Ручная задача редактора'; level.save()
        CareerOffer.objects.filter(pk='lab').update(schedule='Ручное расписание редактора')
        result = self.sync(apply=True)
        self.assertEqual(result['updated'], 1)
        self.assertEqual(result['skipped'], 2)
        level.refresh_from_db()
        self.assertEqual(level.description, 'Ручная задача редактора')
        self.assertEqual(level.explanation, 'Прежнее объяснение учебного сигнала.')
        self.assertEqual(level.versions.count(), before)
        offer = CareerOffer.objects.get(pk='lab')
        self.assertEqual(offer.schedule, 'Ручное расписание редактора')
        self.assertEqual(offer.title, 'Прежнее название практики')

    def test_manually_changed_target_copy_and_structural_puzzle_are_not_overwritten(self):
        LevelDefinition.objects.filter(pk='signal-1').update(explanation='Ручной итог редактора')
        shift = LevelDefinition.objects.get(pk='shift-1')
        shift.puzzle = {**shift.puzzle, 'modelNote': 'Ручная модель редактора'}
        shift.save()
        result = self.sync(apply=True)
        self.assertEqual(result['skipped'], 2)
        self.assertEqual(LevelDefinition.objects.get(pk='signal-1').explanation, 'Ручной итог редактора')
        self.assertEqual(LevelDefinition.objects.get(pk='shift-1').career_explanation, '')

    def test_archived_or_draft_objects_and_manual_fixtures_remain_untouched(self):
        LevelDefinition.objects.filter(pk='signal-1').update(status='draft')
        CareerOffer.objects.filter(pk='lab').update(archived=True)
        shift = LevelDefinition.objects.get(pk='shift-1')
        shift.fixtures['negative'].append({'evidence': []}); shift.save()
        result = self.sync(apply=True)
        self.assertEqual(result['updated'], 0)
        self.assertEqual(result['skipped'], 3)
        self.assertEqual(LevelDefinition.objects.get(pk='signal-1').status, 'draft')
        self.assertTrue(CareerOffer.objects.get(pk='lab').archived)

    def test_baseline_with_mechanics_change_is_not_treated_as_copy(self):
        baseline = copy.deepcopy(self.baseline)
        next(task for task in baseline['tasks'] if task['id'] == 'signal-1')['points'] = 999
        self.baseline_path.write_text(json.dumps(baseline), encoding='utf-8')
        result = self.sync(apply=True)
        signal = next(row for row in result['results'] if row['id'] == 'signal-1')
        self.assertEqual(signal['status'], 'skipped')
        self.assertEqual(signal['reason'], 'non_copy_change')
        self.assertEqual(LevelDefinition.objects.get(pk='signal-1').points, 50)
