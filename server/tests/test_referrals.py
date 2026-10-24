"""Referral tests use isolated schemas and synthetic identities only."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from server.errors import APIError
from server.practice import migrate as migrate_practice
from server.staff_auth import migrate as migrate_staff
from server.referrals import (ALPHABET, bind_application, get_or_create_code, migrate,
                              normalize_code, referral_for_application, referrals_for_applications,
                              mark_hired, mark_reward_issued, merch_rewards)


class ReferralTests(unittest.TestCase):
    def setUp(self):
        self.db = self.database()
        self.add_intern('staff:one', 'Первый Практикант')
        self.add_intern('staff:two', 'Второй Практикант')
        self.db.execute("INSERT INTO users VALUES('candidate',NULL)")
        self.db.execute("INSERT INTO users VALUES('other-candidate',NULL)")
        self.db.commit()

    def tearDown(self):
        self.db.close()

    @staticmethod
    def database(path=':memory:'):
        db = sqlite3.connect(path); db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.executescript('''CREATE TABLE users(id TEXT PRIMARY KEY,profile TEXT);
            CREATE TABLE applications(id TEXT PRIMARY KEY,user_id TEXT REFERENCES users(id),offer TEXT,
            profile TEXT,status TEXT,created TEXT,UNIQUE(user_id,offer));''')
        migrate_practice(db); migrate_staff(db); migrate(db)
        return db

    def add_intern(self, uid, name, *, role='intern', active=1, practice=True, status='active'):
        self.db.execute('INSERT INTO users VALUES(?,?)', (uid, json.dumps({'fullName': name})))
        self.db.execute('INSERT INTO staff_credentials VALUES(?,?,?,?,?)', (uid, uid, 'fixture-not-used-for-login', role, active))
        if practice:
            self.db.execute('''INSERT INTO practices(id,user_id,title,department,start_date,end_date,status,created)
                VALUES(?,?,?,?,?,?,?,?)''', (uid, uid, 'Практика', 'Тестовый отдел', '2026-01-01', '2026-12-31', status, 'fixture-time'))

    def application(self, app='app-one', uid='candidate', offer=None):
        self.db.execute('INSERT INTO applications VALUES(?,?,?,?,?,?)', (app, uid, offer or app, '{}', 'sent', 'fixture-time'))
        return app

    def error(self, code, function, status=422):
        with self.assertRaises(APIError) as caught:
            function()
        self.assertEqual((caught.exception.status, caught.exception.code), (status, code))
        return caught.exception

    def test_stable_random_code_is_per_intern_and_stats_contain_no_candidate_fields(self):
        first = get_or_create_code(self.db, 'staff:one')
        self.assertRegex(first['code'], r'^OC-[A-HJ-NP-Z2-9]{8}$')
        self.assertEqual(first, get_or_create_code(self.db, 'staff:one'))
        self.assertNotEqual(first['code'], get_or_create_code(self.db, 'staff:two')['code'])
        self.assertEqual(first['stats'], {'applications': 0, 'merchPending': 0, 'merchIssued': 0})
        self.application(); bind_application(self.db, 'candidate', 'app-one', first['code'])
        stats = get_or_create_code(self.db, 'staff:one')
        self.assertEqual(set(stats), {'code', 'created', 'stats'})
        self.assertEqual(stats['stats'], {'applications': 1, 'merchPending': 0, 'merchIssued': 0})
        self.assertNotIn('candidate', json.dumps(stats))
        self.assertNotIn('Первый', json.dumps(stats, ensure_ascii=False))

    def test_crypto_collision_retries_and_preserves_previous_owner(self):
        with patch('server.referrals.secrets.choice', return_value='A'):
            first = get_or_create_code(self.db, 'staff:one')
        with patch('server.referrals.secrets.choice', side_effect=['A'] * 8 + ['B'] * 8):
            second = get_or_create_code(self.db, 'staff:two')
        self.assertEqual(first['code'], 'OC-AAAAAAAA')
        self.assertEqual(second['code'], 'OC-BBBBBBBB')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM referral_codes').fetchone()[0], 2)
        self.assertEqual(set(ALPHABET), set('ABCDEFGHJKLMNPQRSTUVWXYZ23456789'))

    def test_requires_active_intern_and_non_cancelled_assigned_practice(self):
        for uid, options in [('staff:mentor', {'role': 'mentor'}), ('staff:inactive', {'active': 0}),
                             ('staff:no-practice', {'practice': False}), ('staff:cancelled', {'status': 'cancelled'})]:
            self.add_intern(uid, 'Имя', **options)
            self.error('referral_forbidden', lambda uid=uid: get_or_create_code(self.db, uid), 403)
        self.error('referral_forbidden', lambda: get_or_create_code(self.db, 'candidate'), 403)
        for status in ['scheduled', 'completed']:
            uid = 'staff:' + status; self.add_intern(uid, 'Имя', status=status)
            self.assertTrue(get_or_create_code(self.db, uid)['code'])

    def test_empty_optional_code_and_normalization(self):
        for empty in ['', ' ', None]:
            app = self.application('app-' + str(empty))
            self.assertIsNone(bind_application(self.db, 'candidate', app, empty))
        code = get_or_create_code(self.db, 'staff:one')['code']
        app = self.application('normalized')
        self.assertEqual(bind_application(self.db, 'candidate', app, '  ' + code.lower() + '  '), {'code': code})
        self.assertEqual(normalize_code(' oc-abcdefgh '), 'OC-ABCDEFGH')

    def test_malformed_unknown_inactive_and_self_do_not_disclose_referrer(self):
        app = self.application()
        for invalid in [False, 12, {}, [], 'OC-AAA', 'OC-ABCDEFGI', 'OC-ABCDEFG0', 'OC-АBCDEFGH', 'OC-ABCD EFGH', 'X' * 65]:
            self.error('referral_invalid', lambda value=invalid: bind_application(self.db, 'candidate', app, value))
        unknown = self.error('referral_unavailable', lambda: bind_application(self.db, 'candidate', app, 'OC-ZZZZZZZZ'))
        code = get_or_create_code(self.db, 'staff:one')['code']
        self.db.execute('UPDATE referral_codes SET active=0 WHERE code=?', (code,))
        inactive = self.error('referral_unavailable', lambda: bind_application(self.db, 'candidate', app, code))
        self.assertEqual(unknown.message, inactive.message)
        self.db.execute('UPDATE referral_codes SET active=1 WHERE code=?', (code,))
        self.db.execute("UPDATE staff_credentials SET active=0 WHERE user_id='staff:one'")
        self.error('referral_unavailable', lambda: bind_application(self.db, 'candidate', app, code))
        self.db.execute("UPDATE staff_credentials SET active=1 WHERE user_id='staff:one'")
        self.application('self', uid='staff:one')
        self.error('referral_self', lambda: bind_application(self.db, 'staff:one', 'self', code))
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM application_referrals').fetchone()[0], 0)

    def test_immutable_attribution_snapshot_and_per_application_policy(self):
        one = get_or_create_code(self.db, 'staff:one')['code']; two = get_or_create_code(self.db, 'staff:two')['code']
        self.application(); bind_application(self.db, 'candidate', 'app-one', one)
        self.assertEqual(bind_application(self.db, 'candidate', 'app-one', two), {'code': one})
        self.assertEqual(bind_application(self.db, 'candidate', 'app-one', 'invalid'), {'code': one})
        self.db.execute("UPDATE users SET profile=? WHERE id='staff:one'", (json.dumps({'fullName': 'Новое Имя'}),))
        self.db.execute("UPDATE referral_codes SET active=0 WHERE user_id='staff:one'")
        admin = referral_for_application(self.db, 'app-one', admin=True)
        self.assertEqual(admin['referrerName'], 'Первый Практикант')
        self.assertEqual(admin['referrerUserId'], 'staff:one')
        self.assertEqual(admin['code'], one)
        self.assertEqual(referral_for_application(self.db, 'app-one'), {'code': one})
        self.application('other-offer'); bind_application(self.db, 'candidate', 'other-offer', two)
        self.assertEqual(get_or_create_code(self.db, 'staff:two')['stats']['applications'], 1)
        self.assertEqual(referrals_for_applications(self.db, ['app-one', 'other-offer', 'app-one', 'absent']),
                         {'app-one': {'code': one}, 'other-offer': {'code': two}})
        self.assertIsNone(referral_for_application(self.db, 'absent'))
        self.assertEqual(referrals_for_applications(self.db, []), {})
        self.error('not_found', lambda: bind_application(self.db, 'other-candidate', 'app-one', two), 404)

    def test_invalid_referral_rolls_back_new_application(self):
        self.db.commit()
        with self.assertRaises(APIError):
            with self.db:
                self.application('rollback')
                bind_application(self.db, 'candidate', 'rollback', 'OC-ZZZZZZZZ')
        self.assertIsNone(self.db.execute("SELECT id FROM applications WHERE id='rollback'").fetchone())
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM application_referrals').fetchone()[0], 0)

    def test_additive_migration_and_restart_preserve_attributions_and_code(self):
        code = get_or_create_code(self.db, 'staff:one')['code']
        self.application(); bind_application(self.db, 'candidate', 'app-one', code)
        self.db.commit(); migrate(self.db)
        self.assertEqual(referral_for_application(self.db, 'app-one'), {'code': code})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'fixture.sqlite3'
            copy = sqlite3.connect(path); self.db.backup(copy); copy.close()
            restarted = sqlite3.connect(path); restarted.row_factory = sqlite3.Row
            migrate(restarted)
            self.assertEqual(get_or_create_code(restarted, 'staff:one')['code'], code)
            self.assertEqual(referral_for_application(restarted, 'app-one', admin=True)['referrerName'], 'Первый Практикант')
            restarted.close()

    def test_merch_requires_explicit_hiring_confirmation_and_is_issued_once(self):
        code = get_or_create_code(self.db, 'staff:one')['code']
        self.application(); bind_application(self.db, 'candidate', 'app-one', code)
        self.db.execute("UPDATE applications SET status='accepted' WHERE id='app-one'")
        self.assertEqual(merch_rewards(self.db), [])
        first = mark_hired(self.db, 'app-one', actor='hr-one')
        self.assertFalse(first['alreadyConfirmed'])
        self.assertEqual(first['reward']['status'], 'pending')
        self.assertIsNone(first['reward']['issuedAt'])
        self.assertEqual(first['reward']['hiredBy'], 'hr-one')
        second = mark_hired(self.db, 'app-one', actor='hr-two')
        self.assertTrue(second['alreadyConfirmed'])
        self.assertEqual(second['reward'], first['reward'])
        self.assertEqual(get_or_create_code(self.db, 'staff:one')['stats'],
                         {'applications': 1, 'merchPending': 1, 'merchIssued': 0})
        issued = mark_reward_issued(self.db, first['reward']['id'], actor='fulfillment-one')
        self.assertFalse(issued['alreadyIssued'])
        self.assertEqual(issued['reward']['status'], 'issued')
        self.assertTrue(issued['reward']['issuedAt'])
        self.assertEqual(issued['reward']['issuedBy'], 'fulfillment-one')
        self.assertEqual(issued['reward']['hiredAt'], first['reward']['hiredAt'])
        repeat = mark_reward_issued(self.db, first['reward']['id'], actor='fulfillment-two')
        self.assertTrue(repeat['alreadyIssued'])
        self.assertEqual(repeat['reward'], issued['reward'])
        self.assertEqual(merch_rewards(self.db), [issued['reward']])
        self.assertEqual(get_or_create_code(self.db, 'staff:one')['stats'],
                         {'applications': 1, 'merchPending': 0, 'merchIssued': 1})
        self.assertEqual(get_or_create_code(self.db, 'staff:two')['stats']['merchIssued'], 0)
        self.assertEqual(referral_for_application(self.db, 'app-one'), {'code': code})

    def test_hiring_retains_referral_snapshot_after_intern_changes(self):
        code = get_or_create_code(self.db, 'staff:one')['code']
        self.application(); bind_application(self.db, 'candidate', 'app-one', code)
        self.db.execute("UPDATE users SET profile=? WHERE id='staff:one'", (json.dumps({'fullName': 'Изменённое Имя'}),))
        self.db.execute("UPDATE staff_credentials SET active=0 WHERE user_id='staff:one'")
        self.db.execute('UPDATE referral_codes SET active=0 WHERE code=?', (code,))
        result = mark_hired(self.db, 'app-one')
        self.assertEqual(result['reward']['referrerName'], 'Первый Практикант')
        self.assertEqual(result['reward']['code'], code)
        self.assertEqual(result['reward']['referrerUserId'], 'staff:one')

    def test_one_hired_candidate_cannot_generate_merch_for_multiple_offers_or_referrers(self):
        one = get_or_create_code(self.db, 'staff:one')['code']
        two = get_or_create_code(self.db, 'staff:two')['code']
        self.application('first-offer'); bind_application(self.db, 'candidate', 'first-offer', one)
        self.application('second-offer'); bind_application(self.db, 'candidate', 'second-offer', two)
        first = mark_hired(self.db, 'second-offer', actor='first-confirming-hr')
        self.assertEqual(first['reward']['referrerUserId'], 'staff:two')
        self.assertEqual(first['reward']['hiredCandidateUserId'], 'candidate')
        self.error('referral_hire_already_confirmed', lambda: mark_hired(self.db, 'first-offer'), 409)
        self.assertTrue(mark_hired(self.db, 'second-offer')['alreadyConfirmed'])
        self.assertEqual(merch_rewards(self.db), [first['reward']])
        self.assertEqual(get_or_create_code(self.db, 'staff:one')['stats']['merchPending'], 0)
        self.assertEqual(get_or_create_code(self.db, 'staff:two')['stats']['merchPending'], 1)

    def test_non_referred_application_missing_rewards_and_invalid_actor(self):
        self.application('not-referred')
        self.error('referral_missing', lambda: mark_hired(self.db, 'not-referred'), 409)
        self.error('not_found', lambda: mark_hired(self.db, 'absent'), 404)
        self.error('not_found', lambda: mark_reward_issued(self.db, 'absent'), 404)
        code = get_or_create_code(self.db, 'staff:one')['code']
        self.application(); bind_application(self.db, 'candidate', 'app-one', code)
        for invalid in [None, '', ' ', False, 'x' * 161]:
            self.error('validation_error', lambda value=invalid: mark_hired(self.db, 'app-one', actor=value))
        self.assertEqual(merch_rewards(self.db), [])
        reward = mark_hired(self.db, 'app-one')['reward']
        for invalid in [None, '', ' ', False, 'x' * 161]:
            self.error('validation_error', lambda value=invalid: mark_reward_issued(self.db, reward['id'], actor=value))
        self.assertEqual(merch_rewards(self.db)[0]['status'], 'pending')

    def test_concurrent_hiring_creates_one_entitlement(self):
        from concurrent.futures import ThreadPoolExecutor
        code = get_or_create_code(self.db, 'staff:one')['code']
        self.application(); bind_application(self.db, 'candidate', 'app-one', code)
        self.db.commit()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'fixture.sqlite3'
            copy = sqlite3.connect(path); self.db.backup(copy); copy.close()
            def hire(index):
                with sqlite3.connect(path, timeout=10) as db:
                    db.row_factory = sqlite3.Row
                    db.execute('BEGIN IMMEDIATE')
                    return mark_hired(db, 'app-one', actor='hr-' + str(index))
            with ThreadPoolExecutor(max_workers=4) as pool:
                results = list(pool.map(hire, range(8)))
            self.assertEqual(sum(not row['alreadyConfirmed'] for row in results), 1)
            self.assertEqual(len({row['reward']['id'] for row in results}), 1)
            self.assertEqual(len({row['reward']['hiredBy'] for row in results}), 1)
            restarted = sqlite3.connect(path); restarted.row_factory = sqlite3.Row
            migrate(restarted)
            self.assertEqual(len(merch_rewards(restarted)), 1)
            self.assertEqual(get_or_create_code(restarted, 'staff:one')['stats']['merchPending'], 1)
            restarted.close()


class ReferralRouteTests(unittest.TestCase):
    def setUp(self):
        import hashlib
        import secrets
        import time
        from server.app import API, Store
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / 'fixture.sqlite3')
        self.api = API(self.store, {'DEV_AUTH': '1', 'ADMIN_TOKEN': 'fixture-admin-only'})
        self.admin = {'X-Admin-Token': 'fixture-admin-only'}
        auth = self.api.dispatch('POST', '/api/auth', {'devUserId': 'referral-candidate'})
        self.candidate = {'Authorization': 'Bearer ' + auth['token']}
        self.api.dispatch('PUT', '/api/profile', {
            'fullName': 'Тестовый Кандидат', 'contact': 'candidate@example.org', 'birthDate': '2000-01-01',
            'direction': 'lab', 'availability': 'Позже', 'education': 'Тестовое обучение', 'consent': True}, self.candidate)
        with self.store.transaction() as db:
            for uid, name in [('staff:first', 'Первый Практикант'), ('staff:second', 'Второй Практикант')]:
                db.execute('INSERT INTO users VALUES(?,?)', (uid, json.dumps({'fullName': name})))
                db.execute('INSERT INTO staff_credentials VALUES(?,?,?,?,1)', (uid, uid, 'fixture-not-used-for-login', 'intern'))
                db.execute("INSERT INTO practices(id,user_id,title,department,start_date,end_date,status,created) VALUES(?,?,?,?,?,?,?,?)",
                           (uid, uid, 'Практика', 'Тест', '2026-01-01', '2026-12-31', 'active', 'fixture-time'))
            self.code = get_or_create_code(db, 'staff:first')['code']
            self.other_code = get_or_create_code(db, 'staff:second')['code']
            token = secrets.token_urlsafe(32)
            db.execute('INSERT INTO sessions VALUES(?,?,?)', (hashlib.sha256(token.encode()).hexdigest(), 'staff:first', time.time() + 3600))
            self.intern = {'Authorization': 'Bearer ' + token}

    def tearDown(self):
        self.temp.cleanup()

    def call(self, method, path, body=None, headers=None):
        return self.api.dispatch(method, path, body, self.candidate if headers is None else headers)

    def expect_error(self, status, function):
        with self.assertRaises(APIError) as caught:
            function()
        self.assertEqual(caught.exception.status, status)

    def test_route_rolls_back_invalid_code_and_preserves_both_kinds_of_original_attribution(self):
        self.expect_error(422, lambda: self.call('POST', '/api/applications', {'offerId': 'lab', 'referralCode': 'OC-ZZZZZZZZ'}))
        self.assertEqual(self.call('GET', '/api/bootstrap')['applications'], [])
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM analytics WHERE event='application_sent'").fetchone()[0], 0)
        first = self.call('POST', '/api/applications', {'offerId': 'lab', 'referralCode': self.code})
        self.assertEqual(first['application']['referral'], {'code': self.code})
        repeat = self.call('POST', '/api/applications', {'offerId': 'lab', 'referralCode': self.other_code})
        self.assertTrue(repeat['alreadyApplied'])
        self.assertEqual(repeat['application']['referral'], {'code': self.code})
        from server.app import CATALOG
        second_offer = next(offer['id'] for offer in CATALOG['offers'] if offer['id'] != 'lab')
        unreferenced = self.call('POST', '/api/applications', {'offerId': second_offer})
        self.assertIsNone(unreferenced['application']['referral'])
        retried = self.call('POST', '/api/applications', {'offerId': second_offer, 'referralCode': self.code})
        self.assertTrue(retried['alreadyApplied'])
        self.assertIsNone(retried['application']['referral'])

    def test_route_separates_candidate_intern_and_hr_payloads_and_permissions(self):
        result = self.call('POST', '/api/applications', {'offerId': 'lab', 'referralCode': self.code})
        app_id = result['application']['id']
        self.expect_error(401, lambda: self.call('GET', '/api/referrals/me'))
        self.expect_error(401, lambda: self.call('GET', '/api/referrals/me', headers={}))
        own = self.call('GET', '/api/referrals/me', headers=self.intern)
        self.assertEqual(own['stats']['applications'], 1)
        self.assertNotIn('candidate', json.dumps(own))
        self.expect_error(401, lambda: self.call('GET', '/api/admin/applications'))
        hr = self.call('GET', '/api/admin/applications', headers=self.admin)['applications']
        item = next(item for item in hr if item['id'] == app_id)
        self.assertEqual(item['referral']['referrerName'], 'Первый Практикант')
        candidate = self.call('GET', '/api/bootstrap')['applications'][0]
        self.assertEqual(candidate['referral'], {'code': self.code})
        self.assertNotIn('staff:first', json.dumps(candidate))

    def test_admin_route_requires_explicit_hire_and_protects_issue_without_points(self):
        app_id = self.call('POST', '/api/applications', {'offerId': 'lab', 'referralCode': self.code})['application']['id']
        self.call('PATCH', '/api/admin/applications/' + app_id, {'status': 'accepted'}, headers=self.admin)
        self.assertEqual(self.call('GET', '/api/admin/referral-rewards', headers=self.admin), {'rewards': []})
        hire = '/api/admin/applications/' + app_id + '/hire'
        self.expect_error(401, lambda: self.call('POST', hire))
        result = self.call('POST', hire, headers=self.admin)
        self.assertFalse(result['alreadyConfirmed'])
        self.assertTrue(self.call('POST', hire, headers=self.admin)['alreadyConfirmed'])
        reward_id = result['reward']['id']
        issue = '/api/admin/referral-rewards/' + reward_id
        self.expect_error(401, lambda: self.call('PATCH', issue, {'status': 'issued'}))
        self.expect_error(422, lambda: self.call('PATCH', issue, {'status': 'pending'}, headers=self.admin))
        issued = self.call('PATCH', issue, {'status': 'issued', 'actor': 'untrusted'}, headers=self.admin)
        self.assertEqual(issued['reward']['issuedBy'], 'hr-admin')
        self.assertTrue(self.call('PATCH', issue, {'status': 'issued'}, headers=self.admin)['alreadyIssued'])
        self.assertEqual(self.call('GET', '/api/referrals/me', headers=self.intern)['stats']['merchIssued'], 1)
        self.assertEqual(self.call('GET', '/api/ledger')['balance'], 0)


if __name__ == '__main__':
    unittest.main()
