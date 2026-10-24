"""Practice domain. Provisioning functions are the integration boundary for the external admin.

No admin UI or self-service role/assignment endpoint is provided here.
All request handlers run inside the API's existing SQLite transaction.
"""
import json
import re
import secrets
from datetime import date, datetime, timedelta, timezone

from .errors import APIError

MSK = timezone(timedelta(hours=3))
PRACTICE_STATUSES = ('scheduled', 'active', 'completed', 'cancelled')
GOAL_STATUSES = ('planned', 'in_progress', 'review', 'approved')
ONBOARDING = ('arrival', 'documents', 'safety', 'team')
SCHEMA = '''
CREATE TABLE IF NOT EXISTS practice_migrations (version INTEGER PRIMARY KEY, applied TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS mentors (
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL UNIQUE REFERENCES users(id),
 name TEXT NOT NULL, position TEXT NOT NULL, contact TEXT NOT NULL,
 about TEXT NOT NULL DEFAULT '', office_hours TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS practices (
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), mentor_id TEXT REFERENCES mentors(id),
 title TEXT NOT NULL, department TEXT NOT NULL, start_date TEXT NOT NULL, end_date TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('scheduled','active','completed','cancelled')),
 coordinator TEXT NOT NULL DEFAULT '{}', arrival TEXT NOT NULL DEFAULT '',
 onboarding TEXT NOT NULL DEFAULT '[]', documents TEXT NOT NULL DEFAULT '[]', created TEXT NOT NULL,
 CHECK(start_date <= end_date)
);
CREATE INDEX IF NOT EXISTS idx_practices_user ON practices(user_id,start_date);
CREATE INDEX IF NOT EXISTS idx_practices_mentor ON practices(mentor_id);
CREATE TABLE IF NOT EXISTS practice_goals (
 id TEXT PRIMARY KEY, practice_id TEXT NOT NULL REFERENCES practices(id), title TEXT NOT NULL,
 description TEXT NOT NULL, criteria TEXT NOT NULL, due_date TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'planned', mentor_comment TEXT NOT NULL DEFAULT '',
 version INTEGER NOT NULL DEFAULT 1, client_key TEXT NOT NULL,
 UNIQUE(practice_id,client_key)
);
CREATE TABLE IF NOT EXISTS practice_meetings (
 id TEXT PRIMARY KEY, practice_id TEXT NOT NULL REFERENCES practices(id), title TEXT NOT NULL,
 starts_at TEXT NOT NULL, ends_at TEXT NOT NULL, location TEXT NOT NULL, agenda TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'scheduled', version INTEGER NOT NULL DEFAULT 1,
 client_key TEXT NOT NULL, UNIQUE(practice_id,client_key)
);
CREATE TABLE IF NOT EXISTS practice_feedback (
 id TEXT PRIMARY KEY, practice_id TEXT NOT NULL REFERENCES practices(id), mentor_id TEXT NOT NULL REFERENCES mentors(id),
 author_name TEXT NOT NULL, body TEXT NOT NULL, created TEXT NOT NULL, client_key TEXT NOT NULL,
 UNIQUE(practice_id,client_key)
);
CREATE TABLE IF NOT EXISTS practice_checkins (
 id TEXT PRIMARY KEY, practice_id TEXT NOT NULL REFERENCES practices(id), week TEXT NOT NULL,
 answers TEXT NOT NULL, created TEXT NOT NULL, UNIQUE(practice_id,week)
);
CREATE TABLE IF NOT EXISTS practice_requests (
 id TEXT PRIMARY KEY, practice_id TEXT NOT NULL REFERENCES practices(id), target TEXT NOT NULL,
 topic TEXT NOT NULL, body TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'received',
 response TEXT NOT NULL DEFAULT '', created TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1,
 client_key TEXT NOT NULL, UNIQUE(practice_id,client_key)
);
CREATE TABLE IF NOT EXISTS practice_career (
 practice_id TEXT PRIMARY KEY REFERENCES practices(id), interested INTEGER NOT NULL,
 direction TEXT NOT NULL, schedule TEXT NOT NULL, comment TEXT NOT NULL, created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS practice_activity (
 id TEXT PRIMARY KEY, practice_id TEXT NOT NULL REFERENCES practices(id), actor_id TEXT NOT NULL REFERENCES users(id),
 event TEXT NOT NULL, created TEXT NOT NULL
);
'''


def stamp():
    return datetime.now(timezone.utc).isoformat()


def new_id():
    return secrets.token_urlsafe(18)


def migrate(db):
    db.executescript(SCHEMA)
    db.execute('INSERT OR IGNORE INTO practice_migrations VALUES(1,?)', (stamp(),))


def field(body, key, maximum=2000, required=False):
    value = body.get(key, '')
    if not isinstance(value, str) or len(value) > maximum or (required and not value.strip()):
        raise APIError(422, f'Проверьте поле «{key}».', 'validation_error')
    return value.strip()


def day(value):
    try:
        if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
            raise ValueError()
        return value
    except (ValueError, TypeError):
        raise APIError(422, 'Укажите дату в формате ГГГГ-ММ-ДД.', 'validation_error')


def instant(value):
    try:
        result = datetime.fromisoformat(value)
        if result.tzinfo is None:
            raise ValueError()
        return result.astimezone(timezone.utc)
    except (TypeError, ValueError):
        raise APIError(422, 'Укажите время с часовым поясом.', 'validation_error')


def client_key(body):
    key = field(body, 'clientKey', 100, True)
    if not re.fullmatch(r'[A-Za-z0-9_-]{8,100}', key):
        raise APIError(422, 'Некорректный ключ отправки.', 'validation_error')
    return key


def activity(db, practice_id, uid, event):
    db.execute('INSERT INTO practice_activity VALUES(?,?,?,?,?)', (new_id(), practice_id, uid, event, stamp()))


def provision_mentor(db, *, user_id, name, position, contact, about='', office_hours=''):
    """Called by the external admin backend after its own permission check."""
    if not db.execute('SELECT 1 FROM users WHERE id=?', (user_id,)).fetchone():
        raise APIError(422, 'Сначала создайте аккаунт наставника.')
    data = {k: v for k, v in locals().items() if k != 'db'}
    name = field(data, 'name', 160, True)
    position = field(data, 'position', 200, True)
    contact = field(data, 'contact', 300, True)
    about = field(data, 'about', 2000)
    office_hours = field(data, 'office_hours', 300)
    db.execute('''INSERT INTO mentors VALUES(?,?,?,?,?,?,?)
                  ON CONFLICT(user_id) DO UPDATE SET name=excluded.name,position=excluded.position,
                  contact=excluded.contact,about=excluded.about,office_hours=excluded.office_hours''',
               (new_id(), user_id, name, position, contact, about, office_hours))
    return db.execute('SELECT id FROM mentors WHERE user_id=?', (user_id,)).fetchone()[0]


def provision_practice(db, *, user_id, title, department, start_date, end_date, mentor_id=None,
                       status='scheduled', coordinator=None, arrival='', documents=None):
    """Create an assigned practice; never inferred from an accepted application."""
    start_date, end_date = day(start_date), day(end_date)
    if start_date > end_date or status not in PRACTICE_STATUSES:
        raise APIError(422, 'Проверьте период и статус практики.')
    if not db.execute('SELECT 1 FROM users WHERE id=?', (user_id,)).fetchone():
        raise APIError(422, 'Аккаунт практиканта не найден.')
    if mentor_id and not db.execute('SELECT 1 FROM mentors WHERE id=?', (mentor_id,)).fetchone():
        raise APIError(422, 'Наставник не найден.')
    data = {'title': title, 'department': department, 'arrival': arrival}
    title, department = field(data, 'title', 200, True), field(data, 'department', 200, True)
    arrival = field(data, 'arrival', 2000)
    coordinator = coordinator or {}
    if not isinstance(coordinator, dict):
        raise APIError(422, 'Проверьте контакт координатора.')
    coordinator = {k: field(coordinator, k, 300) for k in ('name', 'contact')}
    documents = documents or []
    if not isinstance(documents, list) or any(not isinstance(d, dict) for d in documents):
        raise APIError(422, 'Проверьте документы.')
    documents = [{'title': field(d, 'title', 200, True), 'status': field(d, 'status', 200, True)} for d in documents[:20]]
    pid = new_id()
    db.execute('''INSERT INTO practices(id,user_id,mentor_id,title,department,start_date,end_date,status,
               coordinator,arrival,documents,created) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',
               (pid, user_id, mentor_id, title, department, start_date, end_date, status,
                json.dumps(coordinator, ensure_ascii=False), arrival, json.dumps(documents, ensure_ascii=False), stamp()))
    activity(db, pid, user_id, 'practice_assigned')
    return pid


def assign_mentor(db, practice_id, mentor_id):
    if mentor_id and not db.execute('SELECT 1 FROM mentors WHERE id=?', (mentor_id,)).fetchone():
        raise APIError(422, 'Наставник не найден.')
    if not db.execute('UPDATE practices SET mentor_id=? WHERE id=?', (mentor_id, practice_id)).rowcount:
        raise APIError(404, 'Практика не найдена.')


class Practice:
    def __init__(self, config):
        self.config = config

    def access(self, db, uid):
        return {'hasPractice': bool(db.execute('SELECT 1 FROM practices WHERE user_id=?', (uid,)).fetchone()),
                'isMentor': bool(db.execute('SELECT 1 FROM mentors WHERE user_id=?', (uid,)).fetchone())}

    @staticmethod
    def authorize(db, uid, pid, mentor_only=False):
        p = db.execute('SELECT * FROM practices WHERE id=?', (pid,)).fetchone()
        if not p:
            raise APIError(404, 'Практика не найдена.', 'not_found')
        mentor = db.execute('SELECT * FROM mentors WHERE id=? AND user_id=?', (p['mentor_id'], uid)).fetchone()
        owner = p['user_id'] == uid
        if (mentor_only and not mentor) or (not mentor_only and not owner and not mentor):
            raise APIError(404, 'Практика не найдена.', 'not_found')
        return p, bool(mentor), owner

    @staticmethod
    def writable(p):
        if p['status'] in ('completed', 'cancelled'):
            raise APIError(409, 'Практика завершена. Новые изменения недоступны.', 'practice_closed')

    @staticmethod
    def version(body, row):
        if type(body.get('version')) is not int or body['version'] != row['version']:
            raise APIError(409, 'Данные уже изменились. Обновите экран и повторите действие.', 'version_conflict')

    def serialize(self, db, p, uid, owner):
        result = dict(p)
        result.pop('user_id')
        result['coordinator'] = json.loads(p['coordinator']) if owner else None
        result['onboarding'] = json.loads(p['onboarding'])
        result['documents'] = json.loads(p['documents'])
        person = db.execute('SELECT profile FROM users WHERE id=?', (p['user_id'],)).fetchone()
        result['studentName'] = (json.loads(person[0]) if person and person[0] else {}).get('fullName', 'Практикант')
        m = db.execute('SELECT id,name,position,contact,about,office_hours FROM mentors WHERE id=?', (p['mentor_id'],)).fetchone()
        result['mentor'] = dict(m) if m else None
        for key, table, order in [('goals', 'practice_goals', 'due_date,id'),
                                  ('meetings', 'practice_meetings', 'starts_at,id'),
                                  ('feedback', 'practice_feedback', 'created DESC,id')]:
            result[key] = [{k: v for k, v in dict(r).items() if k not in ('practice_id', 'client_key')}
                           for r in db.execute(f'SELECT * FROM {table} WHERE practice_id=? ORDER BY {order}', (p['id'],))]
        # Sensitive answers and career preferences never enter mentor payloads.
        if owner:
            result['checkins'] = [dict(r) for r in db.execute('SELECT id,week,answers,created FROM practice_checkins WHERE practice_id=? ORDER BY week DESC', (p['id'],))]
            for c in result['checkins']:
                c['answers'] = json.loads(c['answers'])
            c = db.execute('SELECT interested,direction,schedule,comment,created FROM practice_career WHERE practice_id=?', (p['id'],)).fetchone()
            result['career'] = dict(c) if c else None
        result['requests'] = [dict(r) for r in db.execute('''SELECT id,target,topic,body,status,response,created,version
                            FROM practice_requests WHERE practice_id=? AND (? OR target='mentor') ORDER BY created DESC''', (p['id'], owner))]
        return result

    def bootstrap(self, db, uid):
        mine = db.execute('SELECT * FROM practices WHERE user_id=? ORDER BY start_date DESC,created DESC', (uid,)).fetchall()
        mentor = db.execute('SELECT id,name,position,contact,about,office_hours FROM mentors WHERE user_id=?', (uid,)).fetchone()
        assigned = db.execute('SELECT * FROM practices WHERE mentor_id=? AND user_id!=? ORDER BY start_date DESC,created DESC',
                              (mentor['id'], uid)).fetchall() if mentor else []
        return {'practices': [self.serialize(db, p, uid, True) for p in mine],
                'mentor': dict(mentor) if mentor else None,
                'mentees': [self.serialize(db, p, uid, False) for p in assigned],
                'today': datetime.now(MSK).date().isoformat(),
                'week': self.week()}

    @staticmethod
    def week():
        today = datetime.now(MSK).date()
        return (today - timedelta(days=today.weekday())).isoformat()

    def dispatch(self, db, uid, method, path, body):
        if method == 'GET' and path == '/api/practice/bootstrap':
            return self.bootstrap(db, uid)
        match = re.fullmatch(r'/api/practice/([^/]+)/(onboarding|goals|meetings|feedback|checkins|requests|career)(?:/([^/]+))?', path)
        if not match:
            raise APIError(404, 'Маршрут практики не найден.', 'not_found')
        pid, kind, item_id = match.groups()
        p, mentor, owner = self.authorize(db, uid, pid)
        self.writable(p)
        if kind in ('onboarding', 'checkins', 'career') and not owner:
            raise APIError(403, 'Действие доступно только практиканту.', 'forbidden')
        if kind == 'onboarding' and method == 'PUT' and not item_id:
            steps = body.get('steps')
            if not isinstance(steps, list) or any(s not in ONBOARDING for s in steps):
                raise APIError(422, 'Проверьте шаги знакомства.', 'validation_error')
            db.execute('UPDATE practices SET onboarding=? WHERE id=?', (json.dumps(sorted(set(steps))), pid))
            return {'saved': True}
        if kind == 'checkins' and method == 'PUT' and not item_id:
            answers = body.get('answers')
            if not isinstance(answers, dict) or any(k not in ('mood', 'comfort', 'workload', 'clarity', 'support', 'comment') for k in answers):
                raise APIError(422, 'Проверьте ответы опроса.', 'validation_error')
            clean = {}
            for k in ('mood', 'comfort', 'workload', 'clarity', 'support'):
                v = answers.get(k)
                if v is not None and (type(v) is not int or not 1 <= v <= 5):
                    raise APIError(422, 'Оценка должна быть от 1 до 5.', 'validation_error')
                clean[k] = v
            clean['comment'] = field(answers, 'comment', 2000)
            db.execute('''INSERT INTO practice_checkins VALUES(?,?,?,?,?) ON CONFLICT(practice_id,week)
                       DO UPDATE SET answers=excluded.answers,created=excluded.created''',
                       (new_id(), pid, self.week(), json.dumps(clean, ensure_ascii=False), stamp()))
            return {'saved': True}
        if kind == 'career' and method == 'PUT' and not item_id:
            if type(body.get('interested')) is not bool:
                raise APIError(422, 'Укажите, хотите ли обсудить продолжение работы.')
            direction, schedule, comment = field(body, 'direction', 300), field(body, 'schedule', 500), field(body, 'comment', 2000)
            db.execute('''INSERT INTO practice_career VALUES(?,?,?,?,?,?) ON CONFLICT(practice_id)
                       DO UPDATE SET interested=excluded.interested,direction=excluded.direction,
                       schedule=excluded.schedule,comment=excluded.comment,created=excluded.created''',
                       (pid, body['interested'], direction, schedule, comment, stamp()))
            activity(db, pid, uid, 'career_interest_updated')
            return {'saved': True}
        if kind == 'requests' and method == 'POST' and not item_id:
            if not owner:
                raise APIError(403, 'Обращение создаёт практикант.', 'forbidden')
            target = body.get('target')
            if target not in ('mentor', 'coordinator') or (target == 'mentor' and not p['mentor_id']):
                raise APIError(422, 'Выберите доступного получателя.')
            topic, message = field(body, 'topic', 200, True), field(body, 'body', 2000, True)
            key = client_key(body)
            db.execute('''INSERT OR IGNORE INTO practice_requests(id,practice_id,target,topic,body,created,client_key)
                        VALUES(?,?,?,?,?,?,?)''', (new_id(), pid, target, topic, message, stamp(), key))
            return {'saved': True, 'id': db.execute('SELECT id FROM practice_requests WHERE practice_id=? AND client_key=?', (pid, key)).fetchone()[0]}
        if kind == 'requests' and method == 'PATCH' and item_id:
            row = db.execute("SELECT * FROM practice_requests WHERE id=? AND practice_id=? AND target='mentor'", (item_id, pid)).fetchone()
            if not mentor or not row:
                raise APIError(404, 'Обращение не найдено.', 'not_found')
            self.version(body, row)
            status = body.get('status')
            if status not in ('received', 'in_progress', 'resolved'):
                raise APIError(422, 'Проверьте статус обращения.')
            response = field(body, 'response', 2000, status == 'resolved')
            db.execute('UPDATE practice_requests SET status=?,response=?,version=version+1 WHERE id=?', (status, response, item_id))
            return {'saved': True}
        if kind == 'goals' and method == 'PATCH' and item_id:
            row = db.execute('SELECT * FROM practice_goals WHERE id=? AND practice_id=?', (item_id, pid)).fetchone()
            if not row:
                raise APIError(404, 'Цель не найдена.', 'not_found')
            self.version(body, row)
            if any(k in body for k in ('title', 'description', 'criteria', 'dueDate')):
                if not mentor:
                    raise APIError(403, 'Цель редактирует наставник.', 'forbidden')
                if row['status'] == 'approved':
                    raise APIError(409, 'Подтверждённую цель нельзя изменить.', 'invalid_transition')
                values = {**dict(row), 'dueDate': row['due_date'], **body}
                title, description, criteria = field(values, 'title', 200, True), field(values, 'description', 2000), field(values, 'criteria', 2000, True)
                due = day(values.get('dueDate'))
                if not p['start_date'] <= due <= p['end_date']:
                    raise APIError(422, 'Срок цели должен попадать в период практики.')
                db.execute('UPDATE practice_goals SET title=?,description=?,criteria=?,due_date=?,version=version+1 WHERE id=?',
                           (title, description, criteria, due, item_id))
                return {'saved': True}
            status = body.get('status')
            allowed = {'planned': ('in_progress',), 'in_progress': ('review',), 'review': (), 'approved': ()}
            if mentor:
                allowed = {'planned': ('in_progress',), 'in_progress': ('review',), 'review': ('approved', 'in_progress'), 'approved': ()}
            if status not in allowed[row['status']]:
                raise APIError(409, 'Этот переход цели недоступен.', 'invalid_transition')
            comment = field(body, 'mentorComment', 2000) if mentor else row['mentor_comment']
            db.execute('UPDATE practice_goals SET status=?,mentor_comment=?,version=version+1 WHERE id=?', (status, comment, item_id))
            activity(db, pid, uid, 'goal_' + status)
            return {'saved': True}
        if kind in ('goals', 'meetings', 'feedback') and method == 'POST' and not item_id:
            if not mentor:
                raise APIError(403, 'Действие доступно только назначенному наставнику.', 'forbidden')
            key = client_key(body)
            if kind == 'goals':
                title, description, criteria = field(body, 'title', 200, True), field(body, 'description', 2000), field(body, 'criteria', 2000, True)
                due = day(body.get('dueDate'))
                if not p['start_date'] <= due <= p['end_date']:
                    raise APIError(422, 'Срок цели должен попадать в период практики.')
                db.execute('''INSERT OR IGNORE INTO practice_goals(id,practice_id,title,description,criteria,due_date,client_key)
                           VALUES(?,?,?,?,?,?,?)''', (new_id(), pid, title, description, criteria, due, key))
            elif kind == 'feedback':
                message = field(body, 'body', 4000, True)
                m = db.execute('SELECT name FROM mentors WHERE id=?', (p['mentor_id'],)).fetchone()
                db.execute('INSERT OR IGNORE INTO practice_feedback VALUES(?,?,?,?,?,?,?)', (new_id(), pid, p['mentor_id'], m['name'], message, stamp(), key))
            else:
                db.execute('''INSERT OR IGNORE INTO practice_meetings(id,practice_id,title,starts_at,ends_at,location,agenda,client_key)
                           VALUES(?,?,?,?,?,?,?,?)''', (new_id(), pid, *self.meeting_values(p, body), key))
            return {'saved': True}
        if kind == 'meetings' and method == 'PATCH' and item_id:
            row = db.execute('SELECT * FROM practice_meetings WHERE id=? AND practice_id=?', (item_id, pid)).fetchone()
            if not mentor or not row:
                raise APIError(404, 'Встреча не найдена.', 'not_found')
            self.version(body, row)
            if 'status' in body:
                if body['status'] not in ('scheduled', 'completed', 'cancelled'):
                    raise APIError(422, 'Проверьте статус встречи.')
                db.execute('UPDATE practice_meetings SET status=?,version=version+1 WHERE id=?', (body['status'], item_id))
            else:
                values = self.meeting_values(p, body)
                db.execute('''UPDATE practice_meetings SET title=?,starts_at=?,ends_at=?,location=?,agenda=?,
                           status='scheduled',version=version+1 WHERE id=?''', (*values, item_id))
            return {'saved': True}
        raise APIError(405, 'Действие недоступно.', 'method_not_allowed')

    @staticmethod
    def meeting_values(p, body):
        title, location, agenda = field(body, 'title', 200, True), field(body, 'location', 300, True), field(body, 'agenda', 2000)
        start, end = instant(body.get('startsAt')), instant(body.get('endsAt'))
        if end - start < timedelta(minutes=1) or end - start > timedelta(hours=12):
            raise APIError(422, 'Встреча должна длиться от минуты до 12 часов.')
        if not (p['start_date'] <= start.astimezone(MSK).date().isoformat() <= end.astimezone(MSK).date().isoformat() <= p['end_date']):
            raise APIError(422, 'Встреча должна попадать в период практики.')
        return title, start.isoformat(), end.isoformat(), location, agenda
