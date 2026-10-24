"""Referral attribution for newly inserted applications; callers own transactions.

Codes are shareable identifiers, never authentication credentials. Candidate DTOs
contain only the submitted code; names and staff IDs are restricted to HR DTOs.
"""
import json
import re
import secrets
from datetime import datetime, timezone

from .errors import APIError

ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
CODE_PATTERN = re.compile(r'OC-[A-HJ-NP-Z2-9]{8}', re.ASCII)
SCHEMA = '''
CREATE TABLE IF NOT EXISTS referral_codes (
 code TEXT PRIMARY KEY, user_id TEXT NOT NULL UNIQUE REFERENCES users(id),
 active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)), created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS application_referrals (
 application_id TEXT PRIMARY KEY REFERENCES applications(id),
 code TEXT NOT NULL REFERENCES referral_codes(code),
 referrer_user_id TEXT NOT NULL REFERENCES users(id),
 referrer_name TEXT NOT NULL, created TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_application_referrals_referrer ON application_referrals(referrer_user_id);
CREATE TABLE IF NOT EXISTS referral_merch_rewards (
 id TEXT PRIMARY KEY, application_id TEXT NOT NULL UNIQUE REFERENCES application_referrals(application_id),
 hired_candidate_user_id TEXT NOT NULL UNIQUE REFERENCES users(id),
 referrer_user_id TEXT NOT NULL REFERENCES users(id), referrer_name TEXT NOT NULL,
 referral_code TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','issued')),
 hired_at TEXT NOT NULL, hired_by TEXT NOT NULL, issued_at TEXT, issued_by TEXT,
 CHECK((status='pending' AND issued_at IS NULL AND issued_by IS NULL)
    OR (status='issued' AND issued_at IS NOT NULL AND issued_by IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS idx_referral_merch_referrer ON referral_merch_rewards(referrer_user_id,status);
'''


def migrate(db):
    db.executescript(SCHEMA)


def stamp():
    return datetime.now(timezone.utc).isoformat()


def eligible(db, uid):
    return bool(db.execute('''SELECT 1 FROM staff_credentials s
        WHERE s.user_id=? AND s.role='intern' AND s.active=1
        AND EXISTS(SELECT 1 FROM practices p WHERE p.user_id=s.user_id AND p.status!='cancelled')''', (uid,)).fetchone())


def _unavailable():
    return APIError(422, 'Этот код недоступен. Проверь его или отправь отклик без кода.', 'referral_unavailable', {'referralCode': 'Код недоступен.'})


def normalize_code(value):
    if value is None:
        return ''
    if not isinstance(value, str) or len(value) > 64:
        raise APIError(422, 'Проверь код практиканта: OC- и 8 букв или цифр.', 'referral_invalid', {'referralCode': 'Проверь формат кода.'})
    value = value.strip().upper()
    if not value:
        return ''
    if not CODE_PATTERN.fullmatch(value):
        raise APIError(422, 'Проверь код практиканта: OC- и 8 букв или цифр.', 'referral_invalid', {'referralCode': 'Проверь формат кода.'})
    return value


def get_or_create_code(db, uid):
    """Active assigned interns only. No commit and no candidate information."""
    if not eligible(db, uid):
        raise APIError(403, 'Реферальный код доступен практиканту с назначенной практикой.', 'referral_forbidden')
    row = db.execute('SELECT code,active,created FROM referral_codes WHERE user_id=?', (uid,)).fetchone()
    if row is None:
        for _ in range(128):
            code = 'OC-' + ''.join(secrets.choice(ALPHABET) for _ in range(8))
            db.execute('INSERT OR IGNORE INTO referral_codes(code,user_id,created) VALUES(?,?,?)', (code, uid, stamp()))
            row = db.execute('SELECT code,active,created FROM referral_codes WHERE user_id=?', (uid,)).fetchone()
            if row is not None:
                break
    if row is None:
        raise APIError(503, 'Не удалось создать код. Попробуй позже.', 'referral_code_unavailable')
    if not row['active']:
        raise APIError(403, 'Реферальный код пока недоступен.', 'referral_forbidden')
    count = db.execute('SELECT COUNT(*) FROM application_referrals WHERE referrer_user_id=?', (uid,)).fetchone()[0]
    rewards = {reward['status']: reward['count'] for reward in db.execute(
        'SELECT status,COUNT(*) AS count FROM referral_merch_rewards WHERE referrer_user_id=? GROUP BY status', (uid,))}
    return {'code': row['code'], 'created': row['created'], 'stats': {
        'applications': count, 'merchPending': rewards.get('pending', 0), 'merchIssued': rewards.get('issued', 0)}}


def _dto(row, admin=False):
    if not row:
        return None
    if not admin:
        return {'code': row['code']}
    return {'code': row['code'], 'referrerUserId': row['referrer_user_id'],
            'referrerName': row['referrer_name'], 'created': row['created']}


def referral_for_application(db, application_id, *, admin=False):
    return _dto(db.execute('SELECT * FROM application_referrals WHERE application_id=?', (application_id,)).fetchone(), admin)


def referrals_for_applications(db, application_ids, *, admin=False):
    """Return metadata keyed by the supplied application IDs; no implicit HR access."""
    result = {}
    ids = list(dict.fromkeys(application_ids))
    # Bound SQL variables for large HR lists without ever interpolating IDs.
    for offset in range(0, len(ids), 500):
        chunk = ids[offset:offset + 500]
        placeholders = ','.join('?' for _ in chunk)
        for row in db.execute(f'SELECT * FROM application_referrals WHERE application_id IN ({placeholders})', chunk):
            result[row['application_id']] = _dto(row, admin)
    return result


def bind_application(db, uid, application_id, code):
    """Bind only after a NEW application INSERT, in that same transaction.

    Root application creation skips this function for alreadyApplied responses,
    including an original application without a referral. Existing attribution is
    immutable even if a caller repeats this function with another code.
    """
    app = db.execute('SELECT user_id FROM applications WHERE id=?', (application_id,)).fetchone()
    if not app or app['user_id'] != uid:
        raise APIError(404, 'Отклик не найден.', 'not_found')
    existing = referral_for_application(db, application_id)
    if existing:
        return existing
    code = normalize_code(code)
    if not code:
        return None
    referral = db.execute('SELECT code,user_id,active FROM referral_codes WHERE code=?', (code,)).fetchone()
    if not referral or not referral['active'] or not eligible(db, referral['user_id']):
        raise _unavailable()
    if referral['user_id'] == uid:
        raise APIError(422, 'Нельзя указать собственный реферальный код.', 'referral_self', {'referralCode': 'Укажи код пригласившего практиканта.'})
    profile = db.execute('SELECT profile FROM users WHERE id=?', (referral['user_id'],)).fetchone()
    try:
        data = json.loads(profile['profile']) if profile and profile['profile'] else {}
        name = data.get('fullName', '') if isinstance(data, dict) else ''
    except (ValueError, TypeError):
        name = ''
    name = name.strip()[:300] if isinstance(name, str) else ''
    db.execute('''INSERT INTO application_referrals(application_id,code,referrer_user_id,referrer_name,created)
        VALUES(?,?,?,?,?)''', (application_id, code, referral['user_id'], name or 'Практикант', stamp()))
    return {'code': code}


def _actor(actor):
    if not isinstance(actor, str) or not actor.strip() or len(actor) > 160:
        raise APIError(422, 'Проверь идентификатор сотрудника, подтвердившего действие.', 'validation_error')
    return actor.strip()


def _reward(row):
    return {'id': row['id'], 'applicationId': row['application_id'], 'hiredCandidateUserId': row['hired_candidate_user_id'],
            'referrerUserId': row['referrer_user_id'], 'referrerName': row['referrer_name'],
            'code': row['referral_code'], 'status': row['status'],
            'hiredAt': row['hired_at'], 'hiredBy': row['hired_by'],
            'issuedAt': row['issued_at'], 'issuedBy': row['issued_by']}


def merch_rewards(db):
    """HR-only serialization boundary; HTTP caller must check admin credentials."""
    return [_reward(row) for row in db.execute('SELECT * FROM referral_merch_rewards ORDER BY hired_at DESC,id')]


def mark_hired(db, application_id, actor='hr-admin'):
    """Explicit HR hiring confirmation, independent from application.status.

    An entitlement is created once per hired candidate, using the first confirmed application. No reward points,
    SKU, delivery promise or automatic hiring priority is inferred here.
    """
    existing = db.execute('SELECT * FROM referral_merch_rewards WHERE application_id=?', (application_id,)).fetchone()
    if existing:
        return {'reward': _reward(existing), 'alreadyConfirmed': True}
    application = db.execute('SELECT user_id FROM applications WHERE id=?', (application_id,)).fetchone()
    if not application:
        raise APIError(404, 'Отклик не найден.', 'not_found')
    candidate = application['user_id']
    if db.execute('SELECT 1 FROM referral_merch_rewards WHERE hired_candidate_user_id=?', (candidate,)).fetchone():
        raise APIError(409, 'Трудоустройство этого кандидата уже подтверждено по другому отклику.', 'referral_hire_already_confirmed')
    referral = db.execute('SELECT * FROM application_referrals WHERE application_id=?', (application_id,)).fetchone()
    if not referral:
        raise APIError(409, 'У этого отклика нет приглашения практиканта.', 'referral_missing')
    actor = _actor(actor)
    db.execute('''INSERT OR IGNORE INTO referral_merch_rewards(
        id,application_id,hired_candidate_user_id,referrer_user_id,referrer_name,referral_code,hired_at,hired_by)
        VALUES(?,?,?,?,?,?,?,?)''', (secrets.token_urlsafe(18), application_id, candidate,
        referral['referrer_user_id'], referral['referrer_name'], referral['code'], stamp(), actor))
    reward = db.execute('SELECT * FROM referral_merch_rewards WHERE application_id=?', (application_id,)).fetchone()
    if not reward:
        if db.execute('SELECT 1 FROM referral_merch_rewards WHERE hired_candidate_user_id=?', (candidate,)).fetchone():
            raise APIError(409, 'Трудоустройство этого кандидата уже подтверждено по другому отклику.', 'referral_hire_already_confirmed')
        raise APIError(503, 'Не удалось сохранить подтверждение. Повтори действие позже.', 'referral_reward_unavailable')
    return {'reward': _reward(reward), 'alreadyConfirmed': False}


def mark_reward_issued(db, reward_id, actor='hr-admin'):
    """Explicit HR fulfillment; repeated calls preserve the first issue snapshot."""
    row = db.execute('SELECT * FROM referral_merch_rewards WHERE id=?', (reward_id,)).fetchone()
    if not row:
        raise APIError(404, 'Право на мерч не найдено.', 'not_found')
    if row['status'] == 'issued':
        return {'reward': _reward(row), 'alreadyIssued': True}
    actor = _actor(actor)
    db.execute("UPDATE referral_merch_rewards SET status='issued',issued_at=?,issued_by=? WHERE id=? AND status='pending'",
               (stamp(), actor, reward_id))
    return {'reward': _reward(db.execute('SELECT * FROM referral_merch_rewards WHERE id=?', (reward_id,)).fetchone()), 'alreadyIssued': False}
