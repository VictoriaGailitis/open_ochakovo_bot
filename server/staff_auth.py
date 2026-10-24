"""Password sign-in for manually provisioned practice accounts. No registration endpoint."""
import hashlib
import hmac
import re
import secrets
import time

from .errors import APIError

ITERATIONS = 600_000
SCHEMA = '''
CREATE TABLE IF NOT EXISTS staff_credentials (
 user_id TEXT PRIMARY KEY REFERENCES users(id), login TEXT NOT NULL UNIQUE,
 password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('intern','mentor')),
 active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1))
);
CREATE TABLE IF NOT EXISTS staff_login_attempts (
 key TEXT PRIMARY KEY, failures INTEGER NOT NULL DEFAULT 0, updated REAL NOT NULL
);
'''


def migrate(db):
    db.executescript(SCHEMA)


def password_hash(password):
    if not isinstance(password, str) or not 12 <= len(password) <= 256:
        raise ValueError('Пароль должен содержать от 12 до 256 символов.')
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), ITERATIONS).hex()
    return f'pbkdf2_sha256${ITERATIONS}${salt}${digest}'


def verify(password, encoded):
    try:
        algorithm, iterations, salt, expected = encoded.split('$')
        if algorithm != 'pbkdf2_sha256' or not 100_000 <= int(iterations) <= 2_000_000:
            return False
        digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), int(iterations)).hex()
        return hmac.compare_digest(digest, expected)
    except (ValueError, TypeError, AttributeError):
        return False


def provision_account(db, *, user_id, login, password, role):
    """Internal provisioning boundary for admin code/CLI, never a public HTTP endpoint."""
    login = login.strip().casefold() if isinstance(login, str) else ''
    if not user_id.startswith('staff:') or role not in ('intern', 'mentor'):
        raise ValueError('Нужны отдельный staff-аккаунт и роль intern или mentor.')
    if not re.fullmatch(r'[a-z0-9][a-z0-9@._+-]{2,119}', login):
        raise ValueError('Некорректный логин.')
    # Do not silently change or reset accounts on a repeated provisioning call.
    if db.execute('SELECT 1 FROM staff_credentials WHERE user_id=? OR login=?', (user_id, login)).fetchone():
        raise ValueError('Учётная запись уже существует.')
    digest = password_hash(password)
    db.execute('INSERT OR IGNORE INTO users(id) VALUES(?)', (user_id,))
    db.execute('INSERT INTO staff_credentials VALUES(?,?,?,?,1)', (user_id, login, digest, role))


def authenticate(db, body, peer):
    login = body.get('login')
    password = body.get('password')
    if not isinstance(login, str) or not isinstance(password, str) or len(login) > 120 or len(password) > 256:
        raise APIError(401, 'Неверный логин или пароль.', 'invalid_credentials')
    login = login.strip().casefold()
    current = time.time()
    key = hashlib.sha256((str(peer) + '\0' + login).encode()).hexdigest()
    db.execute('DELETE FROM staff_login_attempts WHERE updated<?', (current - 900,))
    attempt = db.execute('SELECT failures FROM staff_login_attempts WHERE key=?', (key,)).fetchone()
    if attempt and attempt['failures'] >= 8:
        return None, APIError(429, 'Слишком много попыток. Повтори вход через 15 минут.', 'login_rate_limited')
    row = db.execute('SELECT * FROM staff_credentials WHERE login=?', (login,)).fetchone()
    # Unknown logins perform the same expensive derivation as valid accounts.
    dummy = f'pbkdf2_sha256${ITERATIONS}$' + '0' * 32 + '$' + '0' * 64
    valid = verify(password, row['password_hash'] if row else dummy)
    if not row or not valid or not row['active']:
        db.execute('''INSERT INTO staff_login_attempts VALUES(?,1,?) ON CONFLICT(key)
                   DO UPDATE SET failures=failures+1,updated=excluded.updated''', (key, current))
        # Return the error so failed-attempt counters are committed before raising it.
        return None, APIError(401, 'Неверный логин или пароль.', 'invalid_credentials')
    db.execute('DELETE FROM staff_login_attempts WHERE key=?', (key,))
    token = secrets.token_urlsafe(32)
    db.execute('INSERT INTO sessions VALUES(?,?,?)', (hashlib.sha256(token.encode()).hexdigest(), row['user_id'], current + 12 * 3600))
    return {'token': token, 'role': row['role'], 'userId': row['user_id']}, None


def require_staff(db, uid):
    row = db.execute('SELECT role FROM staff_credentials WHERE user_id=? AND active=1', (uid,)).fetchone()
    if not row:
        raise APIError(401, 'Войди по выданным логину и паролю.', 'staff_login_required')
    return row['role']
