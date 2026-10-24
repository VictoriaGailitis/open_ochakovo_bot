import tempfile
import unittest
import sqlite3
from pathlib import Path
from server.app import API, APIError, Store, ACTIVITY_QR_PREFIX
from server.staff_auth import provision_account, migrate, password_hash, authenticate, require_staff
from server.staff_accounts import create_accounts


class StaffAuthTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / 'auth.db')
        self.api = API(self.store, {})
        with self.store.transaction() as db:
            provision_account(db, user_id='staff:test', login='intern', password='Long-password-123!', role='intern')

    def tearDown(self):
        self.temp.cleanup()

    def login(self, login='intern', password='Long-password-123!'):
        return self.api.dispatch('POST', '/api/staff/login', {'login': login, 'password': password})

    def failure(self, status, call):
        with self.assertRaises(APIError) as error:
            call()
        self.assertEqual(error.exception.status, status)
        return error.exception.message

    def test_password_hash_and_production_login_logout(self):
        with self.store.transaction() as db:
            row = db.execute('SELECT password_hash FROM staff_credentials').fetchone()
            self.assertTrue(row[0].startswith('pbkdf2_sha256$600000$'))
            self.assertNotIn('Long-password', row[0])
        result = self.login(' INTERN ')
        headers = {'Authorization': 'Bearer '+result['token']}
        self.assertEqual(result['role'], 'intern')
        self.assertEqual(self.api.dispatch('GET', '/api/staff/session', headers=headers)['userId'], 'staff:test')
        self.api.dispatch('DELETE', '/api/auth', headers=headers)
        self.failure(401, lambda: self.api.dispatch('GET', '/api/staff/session', headers=headers))

    def test_bad_credentials_and_rate_limit_are_persisted(self):
        message = self.failure(401, lambda: self.login(password='wrong'))
        self.assertEqual(message, self.failure(401, lambda: self.login(login='unknown')))
        for _ in range(7):
            self.failure(401, lambda: self.login(password='wrong'))
        self.failure(429, self.login)
        API(Store(self.store.path), {})
        self.failure(429, self.login)

    def test_disabling_account_revokes_existing_session(self):
        result = self.login()
        with self.store.transaction() as db:
            db.execute('UPDATE staff_credentials SET active=0')
        self.failure(401, lambda: self.api.dispatch('GET', '/api/staff/session', headers={'Authorization':'Bearer '+result['token']}))
        self.failure(401, self.login)

    def test_provisioning_creates_linked_accounts_without_reset(self):
        output = Path(self.temp.name) / 'issued.json'
        issued = create_accounts(self.store, output)
        self.assertEqual(create_accounts(self.store, output), issued)
        self.assertEqual(output.stat().st_mode & 0o777, 0o600)
        for account in issued:
            auth = self.login(account['login'], account['password'])
            self.assertEqual(auth['role'], account['role'])
            data = self.api.dispatch('GET', '/api/practice/bootstrap', headers={'Authorization':'Bearer '+auth['token']})
            self.assertEqual(len(data['mentees' if account['role']=='mentor' else 'practices']), 1)
        with self.store.transaction() as db:
            with self.assertRaises(ValueError):
                provision_account(db, user_id='staff:test', login='intern', password='Replacement-password!', role='mentor')

    def test_employee_login_does_not_require_candidate_profile_or_assigned_practice(self):
        with self.store.transaction() as db:
            provision_account(db, user_id='staff:employee', login='employee', password='Employee-password-123!', role='employee')
            self.assertIsNone(db.execute('SELECT profile FROM users WHERE id=?', ('staff:employee',)).fetchone()[0])
        auth = self.login('employee', 'Employee-password-123!')
        headers = {'Authorization': 'Bearer '+auth['token']}
        self.assertEqual(auth['role'], 'employee')
        self.assertEqual(self.api.dispatch('GET', '/api/staff/session', headers=headers)['role'], 'employee')
        data = self.api.dispatch('GET', '/api/practice/bootstrap', headers=headers)
        self.assertEqual(data['practices'], [])
        self.assertEqual(data['mentees'], [])
        community = self.api.dispatch('GET', '/api/community/bootstrap', headers=headers)
        self.assertEqual(community['user'], {'id': 'staff:employee', 'role': 'employee'})
        self.assertEqual(community['balance'], 0)
        self.assertTrue(community['events'])
        self.assertTrue(all(event['audience'] in ('staff', 'all') for event in community['events']))
        with self.store.transaction() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM applications WHERE user_id=?', ('staff:employee',)).fetchone()[0], 0)

    def test_employee_material_event_activity_and_merch_share_one_ledger_without_registration(self):
        with self.store.transaction() as db:
            provision_account(db, user_id='staff:community', login='community', password='Community-password-123!', role='employee')
            quiz_row = db.execute("SELECT version FROM materials WHERE id='ochakovo-history'").fetchone()
            answers = {row['id']: row['correct_option_id'] for row in db.execute(
                "SELECT id,correct_option_id FROM material_questions WHERE material_id='ochakovo-history' AND version=?", (quiz_row['version'],))}
            activity = db.execute("SELECT id,event_id,qr_token FROM event_activities WHERE event_id='staff-community-day' AND active=1").fetchone()
            code = ACTIVITY_QR_PREFIX + activity['qr_token']
        auth = self.login('community', 'Community-password-123!')
        headers = {'Authorization': 'Bearer '+auth['token']}
        material = self.api.dispatch('GET', '/api/materials/ochakovo-history', headers=headers)['material']
        self.assertTrue(material['quiz']['questions'])
        earned = self.api.dispatch('POST', '/api/materials/ochakovo-history/complete', {'version': material['version'], 'answers': answers}, headers)
        self.assertEqual(earned['pointsAwarded'], 30)
        self.api.dispatch('POST', f"/api/events/{activity['event_id']}/registration", {}, headers)
        scanned = self.api.dispatch('POST', '/api/event-activities/scan', {'code': code}, headers)
        self.assertEqual(scanned['pointsAwarded'], 20)
        self.assertEqual(scanned['balance'], 50)
        exchanged = self.api.dispatch('POST', '/api/rewards/reward-1/exchange', {}, headers)
        self.assertEqual(exchanged['balance'], 0)
        self.assertEqual(self.api.dispatch('POST', '/api/event-activities/scan', {'code': code}, headers)['pointsAwarded'], 0)
        self.assertEqual(self.api.dispatch('POST', '/api/materials/ochakovo-history/complete', {'version': material['version'], 'answers': answers}, headers)['pointsAwarded'], 0)
        self.assertTrue(self.api.dispatch('POST', '/api/rewards/reward-1/exchange', {}, headers)['alreadyExchanged'])
        data = self.api.dispatch('GET', '/api/community/bootstrap', headers=headers)
        self.assertEqual(data['balance'], 0)
        self.assertEqual(sorted(row['delta'] for row in data['ledger']), [-50, 20, 30])
        self.assertEqual(len(data['activityCompletions']), 1)
        self.assertEqual(len(data['exchanges']), 1)
        with self.store.transaction() as db:
            self.assertIsNone(db.execute('SELECT profile FROM users WHERE id=?', ('staff:community',)).fetchone()[0])
            self.assertEqual(db.execute('SELECT COUNT(*) FROM practices WHERE user_id=?', ('staff:community',)).fetchone()[0], 0)

    def test_candidate_session_cannot_be_used_as_a_staff_session(self):
        api = API(self.store, {'DEV_AUTH': '1'})
        candidate = api.dispatch('POST', '/api/auth', {'devUserId': 'demo-staff-isolation'})
        self.failure(401, lambda: api.dispatch('GET', '/api/staff/session', headers={'Authorization': 'Bearer '+candidate['token']}))

    def test_employee_role_migration_preserves_credentials_sessions_and_foreign_keys(self):
        db = sqlite3.connect(':memory:')
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.executescript('''
            CREATE TABLE users(id TEXT PRIMARY KEY, profile TEXT);
            CREATE TABLE sessions(token TEXT PRIMARY KEY, user_id TEXT REFERENCES users(id), expires REAL);
            CREATE TABLE staff_credentials (
                user_id TEXT PRIMARY KEY REFERENCES users(id), login TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('intern','mentor')),
                active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)));
            INSERT INTO users VALUES('staff:old',NULL),('staff:inactive',NULL);
        ''')
        digest = password_hash('Existing-password-123!')
        db.execute('INSERT INTO staff_credentials VALUES(?,?,?,?,?)', ('staff:old', 'old.login', digest, 'mentor', 1))
        db.execute('INSERT INTO staff_credentials VALUES(?,?,?,?,?)', ('staff:inactive', 'inactive', digest, 'intern', 0))
        db.execute("INSERT INTO sessions VALUES('preserved-session','staff:old',9999999999)")
        migrate(db)
        migrate(db)
        rows = [tuple(row) for row in db.execute('SELECT * FROM staff_credentials ORDER BY user_id')]
        self.assertEqual(rows, [('staff:inactive', 'inactive', digest, 'intern', 0), ('staff:old', 'old.login', digest, 'mentor', 1)])
        self.assertEqual(db.execute('SELECT token FROM sessions').fetchone()[0], 'preserved-session')
        self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])
        auth, error = authenticate(db, {'login': 'old.login', 'password': 'Existing-password-123!'}, 'local-test')
        self.assertIsNone(error)
        self.assertEqual(auth['role'], 'mentor')
        provision_account(db, user_id='staff:new', login='new.employee', password='New-employee-password!', role='employee')
        self.assertEqual(require_staff(db, 'staff:new'), 'employee')
        with self.assertRaises(sqlite3.IntegrityError):
            db.execute("INSERT INTO staff_credentials VALUES('staff:no-user','missing','hash','employee',1)")
        db.close()


if __name__ == '__main__':
    unittest.main()
