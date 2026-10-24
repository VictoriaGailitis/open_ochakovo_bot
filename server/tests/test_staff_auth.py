import tempfile
import unittest
from pathlib import Path
from server.app import API, APIError, Store
from server.staff_auth import provision_account
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


if __name__ == '__main__':
    unittest.main()
