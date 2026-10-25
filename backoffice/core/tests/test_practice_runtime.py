"""Practice routes on the actual PostgreSQL transport and staff sessions."""
import json

from django.db import connection
from django.test import Client, TestCase

from backoffice.core.models import PracticeCareer, PracticeCheckin
from server.postgres import runtime_store
from server.practice import provision_mentor, provision_practice
from server.staff_auth import provision_account


class PracticeRuntimeTests(TestCase):
    password = 'Practice-runtime-password-123!'

    @classmethod
    def setUpTestData(cls):
        with runtime_store().transaction() as db:
            for role in ('intern', 'mentor', 'other'):
                provision_account(db, user_id='staff:practice-runtime-' + role,
                                  login='practice-runtime-' + role, password=cls.password,
                                  role='mentor' if role == 'mentor' else 'intern')
            mentor = provision_mentor(db, user_id='staff:practice-runtime-mentor', name='Тестовый наставник',
                                      position='Специалист', contact='mentor@example.invalid')
            cls.practice_id = provision_practice(
                db, user_id='staff:practice-runtime-intern', mentor_id=mentor,
                title='Тестовая практика', department='Учебный отдел',
                start_date='2026-01-01', end_date='2026-12-31', status='active')

    def setUp(self):
        self.assertEqual(connection.vendor, 'postgresql')
        self.client = Client(enforce_csrf_checks=True)
        self.tokens = {}

    def token(self, role):
        if role not in self.tokens:
            response = self.client.post('/api/staff/login', json.dumps({
                'login': 'practice-runtime-' + role, 'password': self.password,
            }), content_type='application/json')
            self.assertEqual(response.status_code, 200)
            self.tokens[role] = response.json()['token']
        return self.tokens[role]

    def call(self, method, path, body=None, role='intern'):
        headers = {'HTTP_AUTHORIZATION': 'Bearer ' + self.token(role)}
        if method == 'GET':
            return self.client.get(path, **headers)
        return self.client.put(path, json.dumps(body), content_type='application/json', **headers)

    def career(self, interested, **kwargs):
        return self.call('PUT', '/api/practice/' + self.practice_id + '/career', {
            'interested': interested, 'direction': 'Лаборатория',
            'schedule': 'После учёбы', 'comment': 'PRIVATE CAREER PREFERENCE',
        }, **kwargs)

    def test_true_false_career_updates_store_integers_and_one_row_on_postgresql(self):
        for interested, stored in [(True, 1), (False, 0), (True, 1)]:
            with self.subTest(interested=interested):
                response = self.career(interested)
                self.assertEqual(response.status_code, 200, response.content)
                self.assertTrue(response.json()['saved'])
                row = PracticeCareer.objects.get(practice_id=self.practice_id)
                self.assertIs(type(row.interested), int)
                self.assertEqual(row.interested, stored)
                own = self.call('GET', '/api/practice/bootstrap').json()['practices'][0]
                self.assertEqual(own['career']['interested'], stored)
        self.assertEqual(PracticeCareer.objects.count(), 1)

    def test_own_private_checkins_and_career_never_enter_mentor_bootstrap(self):
        self.assertEqual(self.career(True).status_code, 200)
        response = self.call('PUT', '/api/practice/' + self.practice_id + '/checkins', {
            'answers': {'mood': 2, 'comfort': 3, 'comment': 'PRIVATE CHECKIN COMMENT'},
        })
        self.assertEqual(response.status_code, 200, response.content)
        own = self.call('GET', '/api/practice/bootstrap').json()['practices'][0]
        self.assertEqual(own['checkins'][0]['answers']['comment'], 'PRIVATE CHECKIN COMMENT')
        self.assertEqual(own['career']['comment'], 'PRIVATE CAREER PREFERENCE')
        mentor_response = self.call('GET', '/api/practice/bootstrap', role='mentor')
        self.assertEqual(mentor_response.status_code, 200, mentor_response.content)
        mentor = mentor_response.json()
        self.assertEqual(mentor['practices'], [])
        self.assertEqual(mentor['mentees'][0]['id'], self.practice_id)
        self.assertNotIn('checkins', mentor['mentees'][0])
        self.assertNotIn('career', mentor['mentees'][0])
        self.assertNotContains(mentor_response, 'PRIVATE CHECKIN COMMENT')
        self.assertNotContains(mentor_response, 'PRIVATE CAREER PREFERENCE')
        denied = self.call('PUT', '/api/practice/' + self.practice_id + '/checkins',
                           {'answers': {'mood': 5}}, role='mentor')
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(self.career(False, role='mentor').status_code, 403)
        self.assertEqual(PracticeCheckin.objects.count(), 1)
        self.assertEqual(PracticeCareer.objects.get(practice_id=self.practice_id).interested, 1)

    def test_other_intern_cannot_read_or_change_assigned_practice(self):
        self.assertEqual(self.career(True).status_code, 200)
        other = self.call('GET', '/api/practice/bootstrap', role='other')
        self.assertEqual(other.status_code, 200)
        self.assertEqual(other.json()['practices'], [])
        self.assertEqual(other.json()['mentees'], [])
        self.assertEqual(self.career(False, role='other').status_code, 404)
        self.assertEqual(PracticeCareer.objects.get(practice_id=self.practice_id).interested, 1)

    def test_non_boolean_career_input_is_rejected_without_overwriting(self):
        self.assertEqual(self.career(True).status_code, 200)
        for invalid in (0, 1, 'true', None):
            with self.subTest(invalid=invalid):
                response = self.career(invalid)
                self.assertEqual(response.status_code, 422)
        self.assertEqual(PracticeCareer.objects.get(practice_id=self.practice_id).interested, 1)
