import copy
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from server.app import API, APIError, Store
from server.practice import assign_mentor, provision_mentor, provision_practice

PROFILE = {'fullName': 'Анна Петрова', 'contact': 'student@example.org', 'birthDate': '2004-01-02',
           'direction': 'lab', 'availability': 'Сейчас', 'education': 'Колледж', 'schedule': '',
           'consent': True, 'futureContact': False}


class PracticeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / 'practice.db')
        self.api = API(self.store, {'DEV_AUTH': '1'})
        self.student = self.login('student')
        self.other = self.login('other')
        self.mentor = self.login('mentor')
        with self.store.transaction() as db:
            self.mid = provision_mentor(db, user_id='demo:mentor', name='Елена Смирнова', position='Наставник', contact='mentor@example.org')
            self.pid = provision_practice(db, user_id='demo:student', title='Лаборатория', department='Качество',
                                          start_date='2026-01-01', end_date='2027-12-31', mentor_id=self.mid, status='active',
                                          coordinator={'name': 'Координатор', 'contact': 'coordinator@example.org'})

    def tearDown(self):
        self.temp.cleanup()

    def login(self, name):
        auth = self.api.dispatch('POST', '/api/auth', {'devUserId': name})
        headers = {'Authorization': 'Bearer ' + auth['token']}
        self.api.dispatch('PUT', '/api/profile', copy.deepcopy(PROFILE), headers)
        return headers

    def call(self, method, kind='bootstrap', body=None, who=None):
        path = '/api/practice/' + (kind if kind in ('bootstrap', 'demo') else self.pid + '/' + kind)
        return self.api.dispatch(method, path, body, who or self.student)

    def expect(self, status, action):
        with self.assertRaises(APIError) as cm:
            action()
        self.assertEqual(cm.exception.status, status, cm.exception.message)

    def placement(self, mentor=False):
        return self.call('GET', who=self.mentor if mentor else None)['mentees' if mentor else 'practices'][0]

    def goal(self):
        self.call('POST', 'goals', {'title': 'Метод анализа', 'description': 'Изучить вместе', 'criteria': 'Объяснить порядок',
                                   'dueDate': '2027-01-01', 'clientKey': 'goal-unique-key'}, self.mentor)
        return self.placement()['goals'][0]

    def test_roles_and_assignment_are_server_side(self):
        self.assertTrue(self.api.dispatch('GET', '/api/bootstrap', headers=self.student)['practiceAccess']['hasPractice'])
        self.assertTrue(self.api.dispatch('GET', '/api/bootstrap', headers=self.mentor)['practiceAccess']['isMentor'])
        self.assertEqual(self.call('GET', who=self.other)['practices'], [])
        self.expect(404, lambda: self.call('PUT', 'onboarding', {'steps': ['arrival']}, self.other))
        self.expect(403, lambda: self.call('POST', 'goals', {'clientKey': 'anything-123'}))
        self.expect(403, lambda: self.call('PUT', 'onboarding', {'steps': []}, self.mentor))
        self.expect(404, lambda: self.call('POST', 'assign', {'mentorId': self.mid}))
        self.expect(401, lambda: self.api.dispatch('GET', '/api/practice/bootstrap'))

    def test_goal_review_and_optimistic_concurrency(self):
        g = self.goal()
        route = 'goals/' + g['id']
        self.expect(409, lambda: self.call('PATCH', route, {'status': 'approved', 'version': 1}))
        self.call('PATCH', route, {'status': 'in_progress', 'version': 1})
        self.expect(409, lambda: self.call('PATCH', route, {'status': 'review', 'version': 1}))
        self.call('PATCH', route, {'status': 'review', 'version': 2, 'mentorComment': 'Не должен сохраниться'})
        self.assertEqual(self.placement()['goals'][0]['mentor_comment'], '')
        self.call('PATCH', route, {'status': 'in_progress', 'version': 3, 'mentorComment': 'Проверь расчёт'}, self.mentor)
        self.assertEqual(self.placement()['goals'][0]['mentor_comment'], 'Проверь расчёт')
        self.call('PATCH', route, {'status': 'review', 'version': 4})
        self.call('PATCH', route, {'status': 'approved', 'version': 5, 'mentorComment': 'Готово'}, self.mentor)
        self.assertEqual(self.placement()['goals'][0]['status'], 'approved')
        self.expect(409, lambda: self.call('PATCH', route, {'version': 6, 'title': 'Подмена'}, self.mentor))

    def test_goal_content_edit_and_cross_practice_ids(self):
        g = self.goal()
        self.expect(403, lambda: self.call('PATCH', 'goals/' + g['id'], {'title': 'Новая', 'version': 1}))
        self.call('PATCH', 'goals/' + g['id'], {'title': 'Новый метод', 'version': 1}, self.mentor)
        self.assertEqual(self.placement()['goals'][0]['title'], 'Новый метод')
        self.expect(422, lambda: self.call('PATCH', 'goals/' + g['id'], {'dueDate': '2030-01-01', 'version': 2}, self.mentor))
        self.expect(404, lambda: self.call('PATCH', 'goals/missing', {'status': 'review', 'version': 1}))

    def test_private_checkins_and_career_never_enter_mentor_bootstrap(self):
        self.call('PUT', 'checkins', {'answers': {'mood': 2, 'comfort': 3, 'comment': 'Личный комментарий'}})
        self.call('PUT', 'checkins', {'answers': {'mood': 4}})
        self.call('PUT', 'career', {'interested': True, 'direction': 'Другое направление', 'schedule': 'После учёбы'})
        own = self.placement()
        self.assertEqual(len(own['checkins']), 1)
        self.assertEqual(own['checkins'][0]['answers']['mood'], 4)
        mentee = self.placement(True)
        self.assertNotIn('checkins', mentee)
        self.assertNotIn('career', mentee)
        self.assertIsNone(mentee['coordinator'])
        self.expect(403, lambda: self.call('PUT', 'checkins', {'answers': {}}, self.mentor))
        self.expect(403, lambda: self.call('PUT', 'career', {'interested': True}, self.mentor))
        for answers in ({'mood': True}, {'mood': 0}, {'comfort': 6}, {'diagnosis': 'x'}, []):
            self.expect(422, lambda: self.call('PUT', 'checkins', {'answers': answers}))

    def test_requests_idempotent_and_recipient_isolation(self):
        body = {'target': 'mentor', 'topic': 'Задача', 'body': 'Нужна помощь', 'clientKey': 'request-unique-123'}
        with ThreadPoolExecutor(max_workers=6) as pool:
            replies = list(pool.map(lambda _: self.call('POST', 'requests', body), range(8)))
        self.assertEqual(len({r['id'] for r in replies}), 1)
        rid = replies[0]['id']
        self.call('POST', 'requests', {**body, 'target': 'coordinator', 'topic': 'Личный вопрос', 'clientKey': 'coordinator-unique'})
        self.assertEqual(len(self.placement()['requests']), 2)
        self.assertEqual(len(self.placement(True)['requests']), 1)
        coordinator_id = next(r['id'] for r in self.placement()['requests'] if r['target'] == 'coordinator')
        self.expect(404, lambda: self.call('PATCH', 'requests/' + coordinator_id, {'version': 1, 'status': 'resolved', 'response': 'x'}, self.mentor))
        self.expect(422, lambda: self.call('PATCH', 'requests/' + rid, {'version': 1, 'status': 'resolved', 'response': ''}, self.mentor))
        self.call('PATCH', 'requests/' + rid, {'version': 1, 'status': 'resolved', 'response': 'Разберём на встрече'}, self.mentor)
        self.assertEqual(next(r for r in self.placement()['requests'] if r['id'] == rid)['response'], 'Разберём на встрече')

    def test_meeting_timezones_reschedule_and_cancel(self):
        body = {'title': 'Встреча', 'startsAt': '2027-01-03T14:00:00+03:00', 'endsAt': '2027-01-03T14:30:00+03:00',
                'location': 'Лаборатория', 'agenda': 'Вопросы', 'clientKey': 'meeting-unique-123'}
        self.call('POST', 'meetings', body, self.mentor)
        self.call('POST', 'meetings', body, self.mentor)
        meetings = self.placement()['meetings']
        self.assertEqual(len(meetings), 1)
        self.assertEqual(meetings[0]['starts_at'], '2027-01-03T11:00:00+00:00')
        mid = meetings[0]['id']
        self.call('PATCH', 'meetings/' + mid, {**body, 'version': 1, 'startsAt': '2027-01-04T14:00:00+03:00', 'endsAt': '2027-01-04T15:00:00+03:00'}, self.mentor)
        self.expect(409, lambda: self.call('PATCH', 'meetings/' + mid, {'version': 1, 'status': 'cancelled'}, self.mentor))
        self.call('PATCH', 'meetings/' + mid, {'version': 2, 'status': 'cancelled'}, self.mentor)
        self.assertEqual(self.placement()['meetings'][0]['status'], 'cancelled')
        for changes in ({'startsAt': '2027-01-03T14:00'}, {'endsAt': body['startsAt']}, {'startsAt': '2030-01-01T14:00:00+03:00'}, {'endsAt': None}):
            self.expect(422, lambda: self.call('POST', 'meetings', {**body, **changes}, self.mentor))

    def test_feedback_keeps_author_and_reassignment_revokes_access(self):
        self.call('POST', 'feedback', {'body': 'Хороший результат', 'clientKey': 'feedback-unique'}, self.mentor)
        self.call('POST', 'feedback', {'body': 'Повтор', 'clientKey': 'feedback-unique'}, self.mentor)
        self.assertEqual(len(self.placement()['feedback']), 1)
        with self.store.transaction() as db:
            mid = provision_mentor(db, user_id='demo:other', name='Новый наставник', position='Специалист', contact='new@example.org')
            assign_mentor(db, self.pid, mid)
        self.assertEqual(self.call('GET', who=self.mentor)['mentees'], [])
        self.expect(404, lambda: self.call('POST', 'feedback', {'body': 'x', 'clientKey': 'new-feedback'}, self.mentor))
        p = self.call('GET', who=self.other)['mentees'][0]
        self.assertEqual(p['feedback'][0]['author_name'], 'Елена Смирнова')
        self.assertEqual(p['mentor']['name'], 'Новый наставник')

    def test_closed_practice_is_read_only_and_data_survives_restart(self):
        self.goal()
        self.call('PUT', 'onboarding', {'steps': ['arrival', 'safety']})
        with self.store.transaction() as db:
            db.execute("UPDATE practices SET status='completed' WHERE id=?", (self.pid,))
        self.expect(409, lambda: self.call('PUT', 'checkins', {'answers': {}}))
        Store(self.store.path)
        self.assertEqual(len(self.placement()['goals']), 1)
        self.assertEqual(self.placement()['onboarding'], ['arrival', 'safety'])
        self.assertEqual(self.placement()['status'], 'completed')

    def test_demo_is_repeatable_and_disabled_for_real_sessions(self):
        headers = self.login('demo-seed')
        first = self.call('POST', 'demo', {}, headers)
        second = self.call('POST', 'demo', {}, headers)
        self.assertEqual(first, second)
        p = self.call('GET', who=headers)['practices'][0]
        self.assertEqual(len(p['goals']), 5)
        self.assertEqual(len(p['meetings']), 1)
        h = self.login(first['mentorDevUserId'])
        self.assertEqual(self.call('GET', who=h)['mentees'][0]['id'], p['id'])
        prod = API(self.store, {})
        self.expect(403, lambda: prod.dispatch('POST', '/api/practice/demo', {}, headers))
        with self.store.transaction() as db:
            db.execute("INSERT INTO users(id) VALUES('vk:123')")
            self.expect(403, lambda: self.api.practice.dispatch(db, 'vk:123', 'POST', '/api/practice/demo', {}))


if __name__ == '__main__':
    unittest.main()
