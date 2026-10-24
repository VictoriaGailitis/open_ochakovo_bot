"""Material privacy, immutable quiz versions and transactional one-time rewards."""
import copy
import json
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from server.app import Store
from server.errors import APIError
from server import learning


def definition(material_id='new-material', audience='all', published=True):
    return {'id': material_id, 'title': 'Учебный материал', 'description': 'Описание материала.',
            'category': 'company', 'audience': audience, 'published': published, 'demo': True,
            'blocks': [{'type': 'heading', 'text': 'Тема'}, {'type': 'text', 'text': 'Факт для изучения.'}],
            'quiz': {'points': 5, 'questions': [{'id': 'question', 'text': 'Выбери ответ.',
                'options': [{'id': 'a', 'text': 'Первый'}, {'id': 'b', 'text': 'Второй'}],
                'correctOptionId': 'a', 'explanation': 'Объяснение после проверки.'}]}}


class LearningTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'learning.db'
        self.store = Store(self.path)
        with self.store.transaction() as db:
            for uid in ('learner', 'other', 'staff'):
                db.execute('INSERT INTO users(id,profile) VALUES(?,NULL)', (uid,))

    def tearDown(self):
        self.temp.cleanup()

    def admin(self, method, path='/api/admin/materials', body=None, validator=None):
        with self.store.transaction() as db:
            return learning.admin(db,method,path,body,validate_media=validator)

    def call(self, method='GET', path='/api/materials', body=None, uid='learner', staff=False):
        with self.store.transaction() as db:
            return learning.dispatch(db,uid,staff,method,path,body)

    def complete(self, material_id='new-material', answers=None, uid='learner', version=1):
        return self.call('POST',f'/api/materials/{material_id}/complete',
                         {'answers': answers if answers is not None else {'question':'a'},'version':version},uid)

    def error(self, status, call):
        with self.assertRaises(APIError) as caught:
            call()
        self.assertEqual(caught.exception.status,status)
        return caught.exception

    def test_candidate_and_staff_visibility_is_enforced_even_when_id_is_known(self):
        self.admin('POST',body=definition('internal','staff'))
        self.admin('POST',body=definition('candidate-only','candidate'))
        self.admin('POST',body=definition('draft','all',False))
        candidate = {item['id'] for item in self.call()['materials']}
        staff = {item['id'] for item in self.call(uid='staff',staff=True)['materials']}
        self.assertIn('candidate-only',candidate)
        self.assertNotIn('candidate-only',staff)
        self.assertIn('internal',staff)
        self.assertNotIn('internal',candidate)
        for material_id in ('internal','draft','unknown'):
            self.error(404,lambda: self.call('GET','/api/materials/'+material_id))
            self.error(404,lambda: self.complete(material_id))
        self.error(404,lambda: self.call('GET','/api/materials/candidate-only',uid='staff',staff=True))

    def test_private_answers_and_explanations_are_not_in_list_or_detail(self):
        self.admin('POST',body=definition())
        for response in [self.call(),self.call('GET','/api/materials/new-material')]:
            serialized=json.dumps(response,ensure_ascii=False)
            self.assertNotIn('correctOptionId',serialized)
            self.assertNotIn('Объяснение после проверки.',serialized)
        public=self.call('GET','/api/materials/new-material')['material']
        self.assertEqual(public['quiz']['questions'][0]['options'][0]['id'],'a')
        private=self.admin('GET','/api/admin/materials/new-material')['material']
        self.assertEqual(private['quiz']['questions'][0]['correctOptionId'],'a')
        wrong=self.complete(answers={'question':'b'})
        self.assertNotIn('explanations',wrong)

    def test_invalid_incomplete_and_incorrect_answers_never_award(self):
        self.admin('POST',body=definition())
        for answers in [{},[],None,{'question':'b'},{'question':['a']},{'question':'a','extra':'a'}]:
            with self.subTest(answers=answers):
                result=self.call('POST','/api/materials/new-material/complete',{'answers':answers,'version':1})
                self.assertFalse(result['correct'])
                self.assertEqual(result['pointsAwarded'],0)
        self.error(422,lambda: self.call('POST','/api/materials/new-material/complete',{'answers':{'question':'a'},'points':1000}))
        with self.store.transaction() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM material_completions').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM ledger').fetchone()[0],0)

    def test_concurrent_and_repeat_completion_pay_once_and_are_user_scoped(self):
        self.admin('POST',body=definition())
        with ThreadPoolExecutor(max_workers=8) as pool:
            results=list(pool.map(lambda _:self.complete(),range(8)))
        self.assertEqual(sum(result['pointsAwarded'] for result in results),5)
        self.assertEqual(sum(not result['alreadyCompleted'] for result in results),1)
        repeat=self.complete()
        self.assertTrue(repeat['alreadyCompleted'])
        self.assertEqual(repeat['balance'],5)
        self.assertEqual(repeat['completion']['awardedPoints'],5)
        self.assertEqual(repeat['explanations'],[{'questionId':'question','text':'Объяснение после проверки.'}])
        self.assertEqual(self.complete(uid='other')['pointsAwarded'],5)
        self.assertIsNone(self.call('GET','/api/materials/new-material',uid='staff')['material']['completion'])

    def test_failure_to_write_ledger_rolls_back_completion(self):
        self.admin('POST',body=definition())
        with self.store.transaction() as db:
            db.execute("CREATE TRIGGER fail_material_award BEFORE INSERT ON ledger BEGIN SELECT RAISE(FAIL,'test failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.complete()
        with self.store.transaction() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM material_completions').fetchone()[0],0)

    def test_versions_preserve_previous_questions_completions_and_stable_reward_key(self):
        self.admin('POST',body=definition())
        self.complete()
        changed=definition()['quiz']
        changed['points']=9
        changed['questions'][0]['correctOptionId']='b'
        update=self.admin('PATCH','/api/admin/materials/new-material',{'quiz':changed,'expectedVersion':1})
        self.assertEqual(update['material']['version'],2)
        self.error(409,lambda: self.complete(version=1))
        self.error(409,lambda: self.admin('PATCH','/api/admin/materials/new-material',{'title':'Stale','expectedVersion':1}))
        repeat=self.complete(answers={'question':'b'},version=2)
        self.assertTrue(repeat['correct'])
        self.assertEqual(repeat['pointsAwarded'],0)
        self.assertEqual(repeat['completion']['version'],1)
        self.assertEqual(repeat['completion']['awardedPoints'],5)
        self.assertEqual(self.complete(answers={'question':'b'},version=2,uid='other')['pointsAwarded'],9)
        with self.store.transaction() as db:
            old=db.execute("SELECT correct_option_id FROM material_questions WHERE material_id='new-material' AND version=1").fetchone()[0]
            self.assertEqual(old,'a')
            self.assertEqual(db.execute("SELECT COUNT(*) FROM material_versions WHERE material_id='new-material'").fetchone()[0],2)
            self.assertEqual(db.execute("SELECT reason FROM ledger WHERE user_id='learner'").fetchone()[0],'material:new-material')

    def test_admin_rejects_invalid_content_quizzes_and_external_media_urls(self):
        variants=[]
        for key,value in [('audience','everybody'),('category','unknown'),('published','yes'),('title',''),('blocks',[])]:
            item=definition();item[key]=value;variants.append(item)
        item=definition();item['quiz']['points']=True;variants.append(item)
        item=definition();item['quiz']['questions'][0]['correctOptionId']='unknown';variants.append(item)
        item=definition();item['quiz']['questions'][0]['options'][1]['id']='a';variants.append(item)
        item=definition();item['quiz']['questions'].append(copy.deepcopy(item['quiz']['questions'][0]));variants.append(item)
        item=definition();item['blocks']=[{'type':'video','mediaId':'https://example.org/video.mp4'}];variants.append(item)
        for item in variants:
            with self.subTest(item=item):
                self.error(422,lambda: self.admin('POST',body=item))
        self.admin('POST',body=definition())
        self.error(409,lambda: self.admin('POST',body=definition()))
        self.error(422,lambda: self.admin('PATCH','/api/admin/materials/new-material',{'id':'renamed'}))

    def test_media_refs_require_audience_validation_and_convert_validation_error(self):
        item=definition()
        item['blocks']=[{'type':'video','mediaId':'asset-1','title':'Видео'}]
        self.error(503,lambda:self.admin('POST',body=item))
        def rejected(db,media_id,audience):
            raise ValueError('Файл закрыт для выбранной аудитории.')
        self.error(422,lambda:self.admin('POST',body=item,validator=rejected))
        calls=[]
        self.admin('POST',body=item,validator=lambda db,media_id,audience:calls.append((media_id,audience)))
        self.assertEqual(calls,[('asset-1','all')])
        self.error(422,lambda:self.admin('PATCH','/api/admin/materials/new-material',{'audience':'candidate'},validator=rejected))

    def test_archive_hides_material_without_deleting_awards_and_seed_preserves_edits(self):
        self.admin('POST',body=definition())
        self.complete()
        self.admin('POST','/api/admin/materials/new-material/archive')
        self.error(404,lambda:self.call('GET','/api/materials/new-material'))
        self.error(404,lambda:self.complete())
        self.error(409,lambda:self.admin('PATCH','/api/admin/materials/new-material',{'title':'Changed'}))
        self.admin('PATCH','/api/admin/materials/practice-first-steps',{'published':False})
        reopened=Store(self.path)
        with reopened.transaction() as db:
            self.assertFalse(db.execute("SELECT published FROM materials WHERE id='practice-first-steps'").fetchone()[0])
            self.assertEqual(db.execute("SELECT SUM(delta) FROM ledger WHERE user_id='learner'").fetchone()[0],5)

    def history_answers(self):
        material=self.admin('GET','/api/admin/materials/ochakovo-history')['material']
        return {question['id']:question['correctOptionId'] for question in material['quiz']['questions']}

    def test_history_material_uses_legacy_reward_and_preserves_route_completion(self):
        result=self.complete('ochakovo-history',self.history_answers())
        self.assertEqual(result['pointsAwarded'],30)
        with self.store.transaction() as db:
            self.assertEqual(db.execute("SELECT reason FROM ledger WHERE user_id='learner'").fetchone()[0],'task:history-1')
            self.assertTrue(db.execute("SELECT completed FROM progress WHERE user_id='learner' AND task='history-1'").fetchone()[0])
        self.assertEqual(self.complete('ochakovo-history',self.history_answers())['pointsAwarded'],0)
        self.error(422,lambda:self.admin('PATCH','/api/admin/materials/ochakovo-history',{'audience':'staff'}))
        self.error(422,lambda:self.admin('PATCH','/api/admin/materials/ochakovo-history',{'published':False}))
        self.error(409,lambda:self.admin('POST','/api/admin/materials/ochakovo-history/archive'))

    def test_legacy_history_completion_or_award_never_earns_a_second_reward(self):
        with self.store.transaction() as db:
            db.execute("INSERT INTO ledger VALUES('old-award','learner','task:history-1',30,'2025-01-01T00:00:00Z')")
            db.execute("INSERT INTO progress(user_id,task,completed) VALUES('other','history-1','2025-01-01T00:00:00Z')")
        for uid,earned in [('learner',30),('other',0)]:
            detail=self.call('GET','/api/materials/ochakovo-history',uid=uid)['material']
            self.assertEqual(detail['completion']['awardedPoints'],earned)
            self.assertEqual(self.complete('ochakovo-history',self.history_answers(),uid=uid)['pointsAwarded'],0)
        reopened=Store(self.path)
        with reopened.transaction() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM material_completions').fetchone()[0],2)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM ledger').fetchone()[0],1)

    def test_seed_quizzes_cover_candidate_practice_and_private_staff_instructions(self):
        candidate={item['id']:item for item in self.call()['materials']}
        staff={item['id']:item for item in self.call(uid='staff',staff=True)['materials']}
        self.assertNotIn('inside-team',candidate)
        self.assertNotIn('practice-first-steps',staff)
        self.assertEqual(candidate['practice-first-steps']['questionCount'],3)
        self.assertEqual(candidate['practice-first-steps']['points'],5)
        self.assertEqual(staff['inside-team']['questionCount'],3)
        self.assertEqual(staff['inside-team']['points'],5)
        self.error(404,lambda:self.call('GET','/api/materials/inside-team'))
        for material_id,uid,is_staff in [('practice-first-steps','learner',False),('inside-team','staff',True)]:
            private=self.admin('GET','/api/admin/materials/'+material_id)['material']
            answers={q['id']:q['correctOptionId'] for q in private['quiz']['questions']}
            result=self.call('POST',f'/api/materials/{material_id}/complete',{'answers':answers,'version':1},uid,is_staff)
            self.assertEqual(result['pointsAwarded'],5)
            self.assertEqual(self.call('POST',f'/api/materials/{material_id}/complete',{'answers':answers,'version':1},uid,is_staff)['pointsAwarded'],0)

    def test_seed_upgrade_adds_practice_quiz_only_to_untouched_former_definition(self):
        with self.store.transaction() as db:
            # Model a database created before the practice quiz was added.
            db.execute("DELETE FROM material_questions WHERE material_id='practice-first-steps'")
            db.execute("UPDATE materials SET points=0 WHERE id='practice-first-steps'")
            learning.seed(db)
            row=db.execute("SELECT version,points FROM materials WHERE id='practice-first-steps'").fetchone()
            self.assertEqual((row['version'],row['points']),(2,5))
        self.admin('PATCH','/api/admin/materials/practice-first-steps',{'title':'Редакция администратора'})
        with self.store.transaction() as db:
            learning.seed(db)
            row=db.execute("SELECT version,title FROM materials WHERE id='practice-first-steps'").fetchone()
            self.assertEqual((row['version'],row['title']),(3,'Редакция администратора'))


if __name__=='__main__':
    unittest.main()
