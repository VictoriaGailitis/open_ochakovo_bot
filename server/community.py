"""Persistent event definitions and audience boundaries shared by both portals."""
import json
import re
import secrets
from datetime import date, time
from .errors import APIError

AUDIENCES = ('candidate', 'staff', 'all')


def migrate(db, catalog):
    db.execute('''CREATE TABLE IF NOT EXISTS career_events (
        id TEXT PRIMARY KEY, definition TEXT NOT NULL,
        audience TEXT NOT NULL CHECK(audience IN ('candidate','staff','all')),
        published INTEGER NOT NULL CHECK(published IN (0,1)))''')
    for event in catalog['events']:
        definition={key:value for key,value in event.items() if key not in ('activities','remaining','audience','published')}
        db.execute('INSERT OR IGNORE INTO career_events VALUES(?,?,?,1)',
                   (event['id'],json.dumps(definition,ensure_ascii=False),event.get('audience','candidate')))
    # An explicitly labelled example makes the employee flow usable before the CMS exists.
    internal={'id':'staff-community-day','title':'Встреча команды · демо','description':'Пример внутреннего мероприятия. Дату и программу организаторы уточнят перед публикацией настоящего события.',
              'date':'2030-12-15','startTime':'15:00','location':'Учебная площадка · демо',
              'type':'Для сотрудников','capacity':50,'demo':True,'program':['Знакомство с командой','Активности на площадке'],'requirements':[]}
    db.execute('INSERT OR IGNORE INTO career_events VALUES(?,?,?,1)',(internal['id'],json.dumps(internal,ensure_ascii=False),'staff'))


def seed_activities(db):
    db.execute('''INSERT OR IGNORE INTO event_activities(id,event_id,title,description,points,active,qr_token)
                  VALUES(?,?,?,?,?,1,?)''',('staff-community-welcome','staff-community-day','Знакомство с командой · демо','Сканируйте QR на площадке после участия во встрече.',20,secrets.token_urlsafe(32)))


def is_staff(db, uid):
    row=db.execute('SELECT active FROM staff_credentials WHERE user_id=?',(uid,)).fetchone() if uid else None
    if row is not None:
        if not row['active']:
            raise APIError(401,'Доступ сотрудника приостановлен.','staff_unauthorized')
        return True
    # A revoked or deleted staff account must not become a public candidate session.
    if uid and uid.startswith('staff:'):
        raise APIError(401,'Доступ сотрудника не подтверждён.','staff_unauthorized')
    return False


def visible(audience, staff):
    return audience in ('all','staff' if staff else 'candidate')


def events(db, staff=False):
    result=[]
    for row in db.execute('SELECT * FROM career_events ORDER BY rowid'):
        if row['published'] and visible(row['audience'],staff):
            result.append({**json.loads(row['definition']),'audience':row['audience'],'published':True})
    return result


def event(db, event_id, staff=False):
    row=db.execute('SELECT * FROM career_events WHERE id=?',(event_id,)).fetchone()
    if not row or not row['published'] or not visible(row['audience'],staff):
        raise APIError(404,'Событие не найдено.','event_not_found')
    return {**json.loads(row['definition']),'audience':row['audience'],'published':True}


def _validate(body):
    if not isinstance(body,dict): raise APIError(422,'Проверьте описание события.')
    result={}
    for field,limit in (('title',200),('description',10000),('location',500),('type',100),('date',10),('startTime',5)):
        value=body.get(field)
        if not isinstance(value,str) or not value.strip() or len(value)>limit:
            raise APIError(422,'Заполните поле '+field+'.','validation_error')
        result[field]=value.strip()
    try:
        date.fromisoformat(result['date']);time.fromisoformat(result['startTime'])
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',result['date']) or not re.fullmatch(r'\d{2}:\d{2}',result['startTime']): raise ValueError()
    except ValueError: raise APIError(422,'Проверьте дату и время события.')
    capacity=body.get('capacity')
    if type(capacity) is not int or not 1<=capacity<=100000: raise APIError(422,'Вместимость должна быть от 1 до 100000.')
    result['capacity']=capacity
    for field in ('program','requirements'):
        values=body.get(field,[])
        if not isinstance(values,list) or len(values)>50 or any(not isinstance(v,str) or not v.strip() or len(v)>2000 for v in values):
            raise APIError(422,'Проверьте поле '+field+'.')
        result[field]=values
    result['demo']=body.get('demo',False) is True
    audience=body.get('audience','candidate');published=body.get('published',False)
    if audience not in AUDIENCES or type(published) is not bool: raise APIError(422,'Проверьте аудиторию и публикацию.')
    return result,audience,int(published)


def admin(db, method, path, body):
    if path=='/api/admin/events' and method=='GET':
        return {'events':[{**json.loads(r['definition']),'audience':r['audience'],'published':bool(r['published'])} for r in db.execute('SELECT * FROM career_events ORDER BY rowid')]}
    match=re.fullmatch(r'/api/admin/events(?:/([A-Za-z0-9_-]+))?',path)
    if not match: raise APIError(404,'Маршрут не найден.','not_found')
    event_id=match[1]
    existing=db.execute('SELECT * FROM career_events WHERE id=?',(event_id,)).fetchone() if event_id else None
    if event_id and not existing: raise APIError(404,'Событие не найдено.','not_found')
    if method=='GET' and existing:
        return {'event':{**json.loads(existing['definition']),'audience':existing['audience'],'published':bool(existing['published'])}}
    if method=='DELETE' and existing:
        db.execute('UPDATE career_events SET published=0 WHERE id=?',(event_id,));return {'archived':True}
    if (method=='POST' and not event_id) or (method in ('PUT','PATCH') and existing):
        merged={**json.loads(existing['definition']),'audience':existing['audience'],'published':bool(existing['published']),**body} if existing else body
        definition,audience,published=_validate(merged)
        event_id=event_id or 'event-'+secrets.token_urlsafe(12)
        definition['id']=event_id
        # Once someone participates, moving the audience would hide their history.
        if existing and audience!=existing['audience'] and (db.execute('SELECT 1 FROM registrations WHERE event=? LIMIT 1',(event_id,)).fetchone() or db.execute('SELECT 1 FROM activity_completions c JOIN event_activities a ON a.id=c.activity_id WHERE a.event_id=? LIMIT 1',(event_id,)).fetchone()):
            raise APIError(409,'У события уже есть участники. Создайте событие для другой аудитории.','audience_locked')
        db.execute('INSERT INTO career_events VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET definition=excluded.definition,audience=excluded.audience,published=excluded.published',(event_id,json.dumps(definition,ensure_ascii=False),audience,published))
        return {'event':{**definition,'audience':audience,'published':bool(published)}}
    raise APIError(405,'Метод не поддерживается.','method_not_allowed')
