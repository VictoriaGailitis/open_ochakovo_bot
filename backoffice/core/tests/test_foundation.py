import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.apps import apps
from django.core.exceptions import ImproperlyConfigured
from django.db import IntegrityError, connection, models, transaction
from django.db.models.deletion import ProtectedError
from django.http import Http404
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings

from backoffice.env import load_environment, postgres_database
from backoffice.static_views import serve_admin_static
from backoffice.core.models import (
    ActivityCompletion, Application, ApplicationReferral, CareerEvent, EventActivity,
    GameProgress, LedgerEntry, Material, MaterialCompletion, MaterialMedia,
    MaterialQuestion, MaterialVersion, MiniUser, Practice, PracticeGoal,
    ReferralCode, ReferralMerchReward, ApiSession, StaffLoginAttempt,
)


class ConfigurationTests(SimpleTestCase):
    def test_credential_object_labels_do_not_disclose_hashes_or_names(self):
        user = MiniUser(id='fixture:user', profile='{"fullName":"Private Name"}')
        session = ApiSession(token='private-session-hash', user=user)
        attempt = StaffLoginAttempt(key='private-login-hash', failures=1, updated=0)
        self.assertEqual(str(user), 'fixture:user')
        self.assertEqual(str(session), 'Сессия пользователя fixture:user')
        self.assertEqual(str(attempt), 'Ограничение попыток входа')

    def test_postgresql_url_only_and_credentials_are_decoded_without_logging(self):
        value = postgres_database('postgresql://app:encoded%40password@127.0.0.1:55432/test_db?sslmode=require')
        self.assertEqual(value['ENGINE'], 'django.db.backends.postgresql')
        self.assertEqual(value['PASSWORD'], 'encoded@password')
        self.assertEqual(value['PORT'], '55432')
        self.assertEqual(value['OPTIONS']['sslmode'], 'require')
        for invalid in ['', 'sqlite:///data.db', 'postgresql://user:sensitive-password@/db']:
            with self.subTest(invalid=invalid.split(':')[0]):
                with self.assertRaises(ImproperlyConfigured) as error:
                    postgres_database(invalid)
                self.assertNotIn('sensitive-password', str(error.exception))

    def test_dotenv_preserves_process_values_and_never_expands_commands(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / '.env'
            path.write_text('FOUNDATION_EXISTING=from-file\nFOUNDATION_QUOTED="space # quoted"\nFOUNDATION_LITERAL="$(do-not-execute)"\n', encoding='utf-8')
            with patch.dict(os.environ, {'FOUNDATION_EXISTING': 'explicit'}, clear=False):
                load_environment(path)
                self.assertEqual(os.environ['FOUNDATION_EXISTING'], 'explicit')
                self.assertEqual(os.environ['FOUNDATION_QUOTED'], 'space # quoted')
                self.assertEqual(os.environ['FOUNDATION_LITERAL'], '$(do-not-execute)')

    def test_public_static_serving_uses_collected_root_and_rejects_traversal(self):
        factory = RequestFactory()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'static'; root.mkdir()
            (root / 'example.css').write_text('body{}', encoding='utf-8')
            (Path(directory) / 'private.txt').write_text('outside', encoding='utf-8')
            with override_settings(DEBUG=False, STATIC_ROOT=root):
                response = serve_admin_static(factory.get('/static/example.css'), 'example.css')
                self.assertEqual(response.status_code, 200)
                self.assertEqual(b''.join(response.streaming_content), b'body{}')
                response.close()
                for path in ['../private.txt', '/etc/passwd', 'missing.css', '']:
                    with self.subTest(path=path), self.assertRaises(Http404):
                        serve_admin_static(factory.get('/static/test'), path)
                self.assertEqual(serve_admin_static(factory.post('/static/example.css'), 'example.css').status_code, 405)


class PostgreSQLCompatibilityTests(TestCase):
    def setUp(self):
        self.assertEqual(connection.vendor, 'postgresql')
        self.user = MiniUser.objects.create(id='fixture:user', profile='{"fullName":"Fixture User"}')

    def material(self, key='fixture-material'):
        return Material.objects.create(id=key, title='Материал', description='', category='company',
                                       audience='all', blocks='[{"type":"text","text":"Содержание"}]')

    def test_all_legacy_columns_exist_with_only_documented_surrogate_additions(self):
        from server.legacy_columns import LEGACY_COLUMNS
        legacy = {table: set(columns) for table, columns in LEGACY_COLUMNS.items()}
        core_models = {model._meta.db_table: model for model in apps.get_app_config('core').get_models()}
        self.assertEqual(set(core_models), set(legacy))
        composites = {'progress', 'activity_completions', 'material_versions', 'material_questions', 'material_completions'}
        with connection.cursor() as cursor:
            for table, model in core_models.items():
                actual = {column.name for column in connection.introspection.get_table_description(cursor, table)}
                extra = {'_pk'} if table == 'material_questions' else {'id'} if table in composites else set()
                self.assertEqual(actual, legacy[table] | extra, table)
                self.assertTrue(model._meta.managed, table)

    def test_raw_legacy_progress_insert_receives_database_revision_default(self):
        with connection.cursor() as cursor:
            cursor.execute('INSERT INTO progress(user_id,task,draft) VALUES(%s,%s,%s)', [self.user.pk, 'fixture-task', '{}'])
        row = GameProgress.objects.get(user=self.user, task='fixture-task')
        self.assertEqual(row.draft_revision, 0)
        self.assertIsInstance(row.pk, int)
        with self.assertRaises(IntegrityError), transaction.atomic():
            GameProgress.objects.create(user=self.user, task='fixture-task')
        self.assertEqual(GameProgress.objects.count(), 1)

    def test_json_and_timestamps_remain_exact_text_and_binary_round_trips(self):
        profile = '{ "fullName": "Имя Фамилия", "unknown": [true, null] }'
        self.user.profile = profile; self.user.save()
        self.user.refresh_from_db()
        self.assertEqual(self.user.profile, profile)
        self.assertIsInstance(self.user.profile, str)
        media = MaterialMedia.objects.create(id='fixture-file', filename='example.png', mime_type='image/png',
                                            audience='all', size=8, content=b'\x89PNG\r\n\x1a\n', created='2026-10-25T01:23:45+00:00')
        media.refresh_from_db()
        self.assertEqual(bytes(media.content), b'\x89PNG\r\n\x1a\n')
        self.assertEqual(media.created, '2026-10-25T01:23:45+00:00')
        self.assertIsInstance(MaterialMedia._meta.get_field('content'), models.BinaryField)
        self.assertIsInstance(Material._meta.get_field('published'), models.IntegerField)
        self.assertNotIsInstance(Material._meta.get_field('published'), models.BooleanField)

    def test_question_identifier_is_distinct_from_admin_primary_key(self):
        material = self.material()
        with connection.cursor() as cursor:
            cursor.execute('''INSERT INTO material_questions(material_id,version,id,position,text,options,correct_option_id,explanation)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s)''', [material.pk, 1, 'question-alpha', 0, 'Вопрос?', '[]', 'a', 'Объяснение'])
            cursor.execute('SELECT id,_pk FROM material_questions WHERE material_id=%s', [material.pk])
            question_id, surrogate = cursor.fetchone()
        row = MaterialQuestion.objects.get(material=material)
        self.assertEqual(question_id, row.question_id)
        self.assertEqual(question_id, 'question-alpha')
        self.assertEqual(surrogate, row.pk)
        self.assertIsInstance(row.pk, int)

    def test_material_versions_and_completion_preserve_original_uniqueness(self):
        material = self.material()
        MaterialVersion.objects.create(material=material, version=1, snapshot='{}')
        MaterialVersion.objects.create(material=material, version=2, snapshot='{}')
        with self.assertRaises(IntegrityError), transaction.atomic():
            MaterialVersion.objects.create(material=material, version=1, snapshot='{"changed":true}')
        MaterialCompletion.objects.create(user=self.user, material=material, version=1, awarded_points=10)
        with self.assertRaises(IntegrityError), transaction.atomic():
            MaterialCompletion.objects.create(user=self.user, material=material, version=2, awarded_points=20)
        self.assertEqual(MaterialCompletion.objects.get(user=self.user, material=material).awarded_points, 10)

    def test_qr_is_random_stable_uneditable_and_flags_have_database_checks(self):
        event = CareerEvent.objects.create(id='fixture-event', definition='{}', audience='all', published=1)
        first = EventActivity.objects.create(event=event, title='Первая', description='', points=10)
        second = EventActivity.objects.create(event=event, title='Вторая', description='', points=20)
        token = first.qr_token
        self.assertEqual(len(token), 43)
        self.assertNotEqual(token, second.qr_token)
        first.title = 'Изменённая'; first.save(); first.refresh_from_db()
        self.assertEqual(first.qr_token, token)
        self.assertFalse(EventActivity._meta.get_field('qr_token').editable)
        with self.assertRaises(IntegrityError), transaction.atomic():
            EventActivity.objects.create(event=event, title='Неверная', description='', points=0)
        ActivityCompletion.objects.create(user=self.user, activity=first, awarded_points=10)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ActivityCompletion.objects.create(user=self.user, activity=first, awarded_points=10)

    def test_database_defaults_make_raw_practice_goal_insert_compatible(self):
        practice = Practice.objects.create(user=self.user, title='Практика', department='Отдел',
                                           start_date='2026-10-01', end_date='2026-11-01', status='active')
        with connection.cursor() as cursor:
            cursor.execute('''INSERT INTO practice_goals(id,practice_id,title,description,criteria,due_date,client_key)
                VALUES(%s,%s,%s,%s,%s,%s,%s)''', ['fixture-goal', practice.pk, 'Цель', '', '', '2026-10-30', 'fixture-key'])
        goal = PracticeGoal.objects.get(pk='fixture-goal')
        self.assertEqual((goal.status, goal.mentor_comment, goal.version), ('planned', '', 1))
        practice.refresh_from_db()
        self.assertEqual((practice.coordinator, practice.onboarding, practice.documents), ('{}', '[]', '[]'))

    def test_ledger_and_foreign_key_history_cannot_be_cascaded_away(self):
        LedgerEntry.objects.create(user=self.user, reason='task:fixture', delta=10)
        with self.assertRaises(IntegrityError), transaction.atomic():
            LedgerEntry.objects.create(user=self.user, reason='task:fixture', delta=10)
        with self.assertRaises(ProtectedError):
            self.user.delete()
        self.assertEqual(LedgerEntry.objects.count(), 1)

    def test_merch_has_one_entitlement_per_hired_person_across_applications(self):
        intern = MiniUser.objects.create(id='fixture:intern')
        code = ReferralCode.objects.create(code='OC-ABCDEFGH', user=intern)
        refs = []
        for index in range(2):
            application = Application.objects.create(user=self.user, offer='offer-' + str(index), profile='{}', status='accepted')
            refs.append(ApplicationReferral.objects.create(application=application, code=code, referrer_user=intern, referrer_name='Имя'))
        ReferralMerchReward.objects.create(application=refs[0], hired_candidate_user=self.user, referrer_user=intern,
                                          referrer_name='Имя', referral_code=code.pk, hired_at='2026-10-25T01:00:00+00:00', hired_by='fixture-admin')
        with self.assertRaises(IntegrityError), transaction.atomic():
            ReferralMerchReward.objects.create(application=refs[1], hired_candidate_user=self.user, referrer_user=intern,
                                              referrer_name='Имя', referral_code=code.pk, hired_at='2026-10-25T01:00:00+00:00', hired_by='fixture-admin')
        self.assertEqual(ReferralMerchReward.objects.count(), 1)
