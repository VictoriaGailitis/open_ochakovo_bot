"""Learning materials and private, versioned quiz definitions.

Root routing authenticates users/admins and wraps writes in one transaction.
Media references are validated by the protected-media domain, never URLs.
"""
import json
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path

from .errors import APIError

CATEGORIES = ('company', 'video', 'practice', 'stories')
AUDIENCES = ('candidate', 'staff', 'all')
HISTORY_MATERIAL = 'ochakovo-history'
LEGACY_HISTORY_TASK = 'history-1'
ID = re.compile(r'[A-Za-z0-9_-]{1,128}\Z')
SCHEMA = '''
CREATE TABLE IF NOT EXISTS materials (
 id TEXT PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL,
 category TEXT NOT NULL CHECK(category IN ('company','video','practice','stories')),
 audience TEXT NOT NULL CHECK(audience IN ('candidate','staff','all')),
 published INTEGER NOT NULL DEFAULT 0 CHECK(published IN (0,1)),
 archived INTEGER NOT NULL DEFAULT 0 CHECK(archived IN (0,1)),
 blocks TEXT NOT NULL, points INTEGER NOT NULL DEFAULT 0 CHECK(points BETWEEN 0 AND 1000),
 version INTEGER NOT NULL DEFAULT 1, demo INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS material_versions (
 material_id TEXT NOT NULL REFERENCES materials(id), version INTEGER NOT NULL,
 snapshot TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(material_id,version)
);
CREATE TABLE IF NOT EXISTS material_questions (
 material_id TEXT NOT NULL REFERENCES materials(id), version INTEGER NOT NULL,
 id TEXT NOT NULL, position INTEGER NOT NULL, text TEXT NOT NULL, options TEXT NOT NULL,
 correct_option_id TEXT NOT NULL, explanation TEXT NOT NULL,
 PRIMARY KEY(material_id,version,id), UNIQUE(material_id,version,position)
);
CREATE TABLE IF NOT EXISTS material_completions (
 user_id TEXT NOT NULL REFERENCES users(id), material_id TEXT NOT NULL REFERENCES materials(id),
 version INTEGER NOT NULL, completed_at TEXT NOT NULL, awarded_points INTEGER NOT NULL,
 PRIMARY KEY(user_id,material_id)
);
CREATE INDEX IF NOT EXISTS idx_materials_visibility ON materials(published,archived,audience,category);
'''


def stamp():
    return datetime.now(timezone.utc).isoformat()


def migrate(db):
    db.executescript(SCHEMA)


def _invalid(message='Проверьте поля материала.'):
    raise APIError(422, message, 'validation_error')


def _text(value, maximum, required=False):
    if not isinstance(value, str) or len(value) > maximum or (required and not value.strip()):
        _invalid()
    return value.strip()


def _id(value):
    if not isinstance(value, str) or not ID.fullmatch(value):
        _invalid('Некорректный идентификатор.')
    return value


def _definition(body, validate_media=None, db=None):
    if not isinstance(body, dict):
        _invalid()
    allowed = {'id', 'title', 'description', 'category', 'audience', 'published', 'blocks', 'quiz', 'demo', 'expectedVersion'}
    if set(body) - allowed:
        _invalid('В определении есть неизвестные поля.')
    title = _text(body.get('title'), 200, True)
    description = _text(body.get('description', ''), 1000)
    category, audience = body.get('category'), body.get('audience')
    if category not in CATEGORIES or audience not in AUDIENCES:
        _invalid('Выберите категорию и аудиторию материала.')
    published, demo = body.get('published', False), body.get('demo', False)
    if type(published) is not bool or type(demo) is not bool:
        _invalid()
    blocks = body.get('blocks')
    if not isinstance(blocks, list) or not 1 <= len(blocks) <= 40:
        _invalid('Добавьте от 1 до 40 блоков материала.')
    normalized = []
    for block in blocks:
        if not isinstance(block, dict):
            _invalid()
        kind = block.get('type')
        if kind in ('text', 'heading'):
            if set(block) != {'type', 'text'}:
                _invalid()
            normalized.append({'type': kind, 'text': _text(block['text'], 10000 if kind == 'text' else 300, True)})
        elif kind in ('video', 'image'):
            allowed_fields = {'type', 'mediaId', 'title'} if kind == 'video' else {'type', 'mediaId', 'alt'}
            if set(block) - allowed_fields:
                _invalid('Медиа-блок принимает только идентификатор загруженного файла.')
            media_id = _id(block.get('mediaId'))
            if validate_media is None:
                raise APIError(503, 'Проверка загруженных файлов пока недоступна.', 'media_not_configured')
            try:
                validate_media(db, media_id, audience)
            except ValueError as error:
                _invalid(str(error))
            label = 'title' if kind == 'video' else 'alt'
            normalized.append({'type': kind, 'mediaId': media_id, label: _text(block.get(label, ''), 500, kind == 'image')})
        else:
            _invalid('Неизвестный тип блока материала.')
    quiz = body.get('quiz')
    questions, points = [], 0
    if quiz is not None:
        if not isinstance(quiz, dict) or set(quiz) != {'points', 'questions'}:
            _invalid('Проверьте определение теста.')
        points = quiz['points']
        if type(points) is not int or not 1 <= points <= 1000:
            _invalid('За тест можно назначить от 1 до 1 000 баллов.')
        if not isinstance(quiz['questions'], list) or not 1 <= len(quiz['questions']) <= 10:
            _invalid('Короткий тест должен содержать от 1 до 10 вопросов.')
        seen = set()
        for question in quiz['questions']:
            if not isinstance(question, dict) or set(question) - {'id', 'text', 'options', 'correctOptionId', 'explanation'}:
                _invalid('Проверьте поля вопроса.')
            question_id = _id(question.get('id'))
            if question_id in seen:
                _invalid('Идентификаторы вопросов должны различаться.')
            seen.add(question_id)
            options = question.get('options')
            if not isinstance(options, list) or not 2 <= len(options) <= 6:
                _invalid('Добавьте от 2 до 6 вариантов ответа.')
            option_ids, normalized_options = set(), []
            for option in options:
                if not isinstance(option, dict) or set(option) != {'id', 'text'}:
                    _invalid()
                option_id = _id(option['id'])
                if option_id in option_ids:
                    _invalid('Идентификаторы вариантов должны различаться.')
                option_ids.add(option_id)
                normalized_options.append({'id': option_id, 'text': _text(option['text'], 1000, True)})
            correct = question.get('correctOptionId')
            if not isinstance(correct, str) or correct not in option_ids:
                _invalid('Правильный ответ должен ссылаться на вариант этого вопроса.')
            questions.append({'id': question_id, 'text': _text(question.get('text'), 2000, True), 'options': normalized_options,
                              'correctOptionId': correct, 'explanation': _text(question.get('explanation', ''), 3000)})
    return {'title': title, 'description': description, 'category': category, 'audience': audience,
            'published': published, 'demo': demo, 'blocks': normalized, 'quiz': {'points': points, 'questions': questions} if questions else None}


def _write(db, material_id, value, version, created):
    updated = stamp()
    points = value['quiz']['points'] if value['quiz'] else 0
    db.execute('''INSERT INTO materials(id,title,description,category,audience,published,archived,blocks,points,version,demo,created_at,updated_at)
                  VALUES(?,?,?,?,?,?,0,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET title=excluded.title,description=excluded.description,
                  category=excluded.category,audience=excluded.audience,published=excluded.published,blocks=excluded.blocks,
                  points=excluded.points,version=excluded.version,demo=excluded.demo,updated_at=excluded.updated_at''',
               (material_id,value['title'],value['description'],value['category'],value['audience'],int(value['published']),
                json.dumps(value['blocks'],ensure_ascii=False),points,version,int(value['demo']),created,updated))
    db.execute('INSERT INTO material_versions VALUES(?,?,?,?)',
               (material_id,version,json.dumps(value,ensure_ascii=False),updated))
    for index, question in enumerate(value['quiz']['questions'] if value['quiz'] else []):
        db.execute('INSERT INTO material_questions VALUES(?,?,?,?,?,?,?,?)',
                   (material_id,version,question['id'],index,question['text'],json.dumps(question['options'],ensure_ascii=False),
                    question['correctOptionId'],question['explanation']))


def seed(db):
    definitions = json.loads(Path(__file__).with_name('learning-seed.json').read_text(encoding='utf-8'))
    for body in definitions['materials']:
        material_id = _id(body['id'])
        current = db.execute('SELECT * FROM materials WHERE id=?', (material_id,)).fetchone()
        if not current:
            _write(db, material_id, _definition(body), 1, stamp())
        elif material_id == 'practice-first-steps' and current['version'] == 1 and current['points'] == 0 and not current['archived']:
            # Add the new quiz only to the exact untouched, former text-only seed.
            # Any edited version, draft or custom content remains authoritative.
            unchanged = (all(current[key] == body[key] for key in ('title','description','category','audience'))
                         and bool(current['published']) == body['published'] and bool(current['demo']) == body['demo']
                         and json.loads(current['blocks']) == body['blocks'])
            if unchanged and body.get('quiz'):
                _write(db,material_id,_definition(body),2,current['created_at'])
    # Compatibility is intentionally restricted to this canonical seed material.
    # Existing historical awards are never repeated under a second reason.
    db.execute("""INSERT OR IGNORE INTO material_completions(user_id,material_id,version,completed_at,awarded_points)
                  SELECT p.user_id,?,1,p.completed,COALESCE(l.delta,0) FROM progress p
                  LEFT JOIN ledger l ON l.user_id=p.user_id AND l.reason=? WHERE p.task=? AND p.completed IS NOT NULL AND p.completed<>''""",
               (HISTORY_MATERIAL,'task:'+LEGACY_HISTORY_TASK,LEGACY_HISTORY_TASK))
    db.execute('''INSERT OR IGNORE INTO material_completions(user_id,material_id,version,completed_at,awarded_points)
                  SELECT user_id,?,1,created,delta FROM ledger WHERE reason=?''',
               (HISTORY_MATERIAL,'task:'+LEGACY_HISTORY_TASK))


def _row(db, material_id, is_staff=None):
    if not isinstance(material_id, str):
        raise APIError(404, 'Материал не найден.', 'material_not_found')
    row = db.execute('SELECT * FROM materials WHERE id=?', (material_id,)).fetchone()
    if not row or (is_staff is not None and (not row['published'] or row['archived'] or row['audience'] not in ('all', 'staff' if is_staff else 'candidate'))):
        raise APIError(404, 'Материал не найден.', 'material_not_found')
    return row


def _questions(db, row, private=False):
    result = []
    for question in db.execute('SELECT * FROM material_questions WHERE material_id=? AND version=? ORDER BY position', (row['id'],row['version'])):
        value = {'id': question['id'], 'text': question['text'], 'options': json.loads(question['options'])}
        if private:
            value.update(correctOptionId=question['correct_option_id'], explanation=question['explanation'])
        result.append(value)
    return result


def _completion(db, uid, material_id):
    row = db.execute('SELECT * FROM material_completions WHERE user_id=? AND material_id=?', (uid,material_id)).fetchone()
    if row:
        return {'materialId': row['material_id'], 'version': row['version'], 'completedAt': row['completed_at'], 'awardedPoints': row['awarded_points']}
    if material_id == HISTORY_MATERIAL:
        legacy = db.execute("SELECT completed FROM progress WHERE user_id=? AND task=? AND completed IS NOT NULL AND completed<>''", (uid,LEGACY_HISTORY_TASK)).fetchone()
        award = db.execute('SELECT created,delta FROM ledger WHERE user_id=? AND reason=?', (uid,'task:'+LEGACY_HISTORY_TASK)).fetchone()
        if legacy or award:
            return {'materialId': material_id, 'version': 1, 'completedAt': legacy['completed'] if legacy else award['created'], 'awardedPoints': award['delta'] if award else 0}
    return None


def _serialize(db, row, uid=None, detail=False, private=False):
    count = db.execute('SELECT COUNT(*) FROM material_questions WHERE material_id=? AND version=?', (row['id'],row['version'])).fetchone()[0]
    value = {'id': row['id'], 'title': row['title'], 'description': row['description'], 'category': row['category'],
             'audience': row['audience'], 'version': row['version'], 'published': bool(row['published']),
             'demo': bool(row['demo']), 'points': row['points'], 'questionCount': count,
             'updatedAt': row['updated_at'], 'completion': _completion(db,uid,row['id']) if uid else None}
    if detail:
        value['blocks'] = json.loads(row['blocks'])
        value['quiz'] = {'points': row['points'], 'questions': _questions(db,row,private)} if count else None
    if private:
        value.update(archived=bool(row['archived']), createdAt=row['created_at'])
    return value


def dispatch(db, uid, is_staff, method, path, body=None):
    if method == 'GET' and path == '/api/materials':
        audience = 'staff' if is_staff else 'candidate'
        rows = db.execute("SELECT * FROM materials WHERE published=1 AND archived=0 AND audience IN ('all',?) ORDER BY created_at,id", (audience,))
        return {'materials': [_serialize(db,row,uid) for row in rows]}
    match = re.fullmatch(r'/api/materials/([A-Za-z0-9_-]{1,128})(/complete)?', path)
    if not match:
        raise APIError(404, 'Материал не найден.', 'material_not_found')
    row = _row(db, match[1], bool(is_staff))
    if method == 'GET' and not match[2]:
        return {'material': _serialize(db,row,uid,detail=True)}
    if method != 'POST' or not match[2]:
        raise APIError(404, 'Материал не найден.', 'material_not_found')
    questions = _questions(db,row,private=True)
    if not questions:
        raise APIError(409, 'У этого материала нет теста.', 'material_no_quiz')
    if not isinstance(body, dict) or set(body) - {'answers', 'version'}:
        _invalid('Передайте ответы на вопросы теста.')
    if 'version' in body and (type(body['version']) is not int or body['version'] != row['version']):
        raise APIError(409, 'Материал обновился. Откройте его заново перед проверкой.', 'material_changed')
    answers = body.get('answers')
    valid = isinstance(answers, dict) and set(answers) == {q['id'] for q in questions}
    correct = valid and all(isinstance(answers[q['id']],str) and answers[q['id']] == q['correctOptionId'] for q in questions)
    balance = lambda: db.execute('SELECT COALESCE(SUM(delta),0) FROM ledger WHERE user_id=?', (uid,)).fetchone()[0]
    if not correct:
        return {'correct': False, 'errors': ['Ответьте на все вопросы и сопоставьте ответы с материалом. Правильными должны быть все ответы.'],
                'pointsAwarded': 0, 'alreadyCompleted': False, 'balance': balance()}
    completion = _completion(db,uid,row['id'])
    awarded = 0
    if not completion:
        reason = 'task:' + LEGACY_HISTORY_TASK if row['id'] == HISTORY_MATERIAL else 'material:' + row['id']
        previous_award = db.execute('SELECT delta FROM ledger WHERE user_id=? AND reason=?', (uid,reason)).fetchone()
        historical = previous_award[0] if previous_award else row['points']
        db.execute('INSERT INTO material_completions VALUES(?,?,?,?,?)', (uid,row['id'],row['version'],stamp(),historical))
        if not previous_award:
            db.execute('INSERT INTO ledger VALUES(?,?,?,?,?)', (secrets.token_urlsafe(18),uid,reason,row['points'],stamp()))
            awarded = row['points']
        completion = _completion(db,uid,row['id'])
    if row['id'] == HISTORY_MATERIAL:
        db.execute('''INSERT INTO progress(user_id,task,draft,completed) VALUES(?,?,'{}',CURRENT_TIMESTAMP)
                      ON CONFLICT(user_id,task) DO UPDATE SET completed=COALESCE(progress.completed,excluded.completed)''', (uid,LEGACY_HISTORY_TASK))
    return {'correct': True, 'errors': [], 'pointsAwarded': awarded, 'alreadyCompleted': awarded == 0,
            'balance': balance(), 'completion': completion,
            'explanations': [{'questionId': q['id'], 'text': q['explanation']} for q in questions if q['explanation']]}


def admin(db, method, path, body=None, validate_media=None):
    """Trusted root admin routing must authorize before entering this function."""
    if path == '/api/admin/materials':
        if method == 'GET':
            return {'materials': [_serialize(db,row,private=True) for row in db.execute('SELECT * FROM materials ORDER BY created_at,id')]}
        if method == 'POST':
            value = _definition(body,validate_media,db)
            material_id = _id(body['id']) if 'id' in body else secrets.token_urlsafe(18)
            _canonical(material_id,value)
            if db.execute('SELECT 1 FROM materials WHERE id=?', (material_id,)).fetchone():
                raise APIError(409, 'Идентификатор материала уже используется.', 'material_conflict')
            _write(db,material_id,value,1,stamp())
            return {'material': _serialize(db,_row(db,material_id),detail=True,private=True)}
    match = re.fullmatch(r'/api/admin/materials/([A-Za-z0-9_-]{1,128})(/archive)?', path)
    if not match:
        raise APIError(404, 'Материал не найден.', 'material_not_found')
    row = _row(db,match[1])
    if method == 'GET' and not match[2]:
        return {'material': _serialize(db,row,detail=True,private=True)}
    if method == 'POST' and match[2]:
        if row['id'] == HISTORY_MATERIAL:
            raise APIError(409, 'Исторический материал сохраняет публичный вход в учебный маршрут.', 'material_canonical')
        db.execute('UPDATE materials SET archived=1,published=0,updated_at=? WHERE id=?', (stamp(),row['id']))
        return {'material': _serialize(db,_row(db,row['id']),detail=True,private=True)}
    if method in ('PUT', 'PATCH') and not match[2]:
        if not isinstance(body, dict):
            _invalid()
        if row['archived']:
            raise APIError(409, 'Архивный материал нельзя редактировать.', 'material_archived')
        if 'id' in body and body['id'] != row['id']:
            _invalid('Идентификатор материала нельзя менять.')
        if 'expectedVersion' in body and (type(body['expectedVersion']) is not int or body['expectedVersion'] != row['version']):
            raise APIError(409, 'Материал уже изменён. Загрузите актуальную версию.', 'material_changed')
        current = _serialize(db,row,detail=True,private=True)
        editable = {key: current[key] for key in ('title','description','category','audience','published','blocks','quiz','demo')}
        value = _definition({**editable,**body},validate_media,db)
        _canonical(row['id'],value)
        _write(db,row['id'],value,row['version']+1,row['created_at'])
        return {'material': _serialize(db,_row(db,row['id']),detail=True,private=True)}
    raise APIError(404, 'Материал не найден.', 'material_not_found')


def _canonical(material_id, value):
    if material_id == HISTORY_MATERIAL and (value['audience'] != 'all' or not value['published'] or not value['quiz'] or value['quiz']['points'] != 30):
        _invalid('Исторический материал должен оставаться общедоступным и опубликованным, с тестом на 30 баллов.')
