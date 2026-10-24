"""Dependency-free API for Ochakovo VK Mini App. Run with python3 -m server."""
import base64
import copy
import hashlib
import hmac
import ipaddress
import json
import mimetypes
import os
import re
import secrets
import sqlite3
import time
from contextlib import closing, contextmanager
from datetime import date, datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, unquote
from .solutions import validate
from .shift import assess as assess_shift, normalize_draft as normalize_shift_draft, completion_details as shift_completion_details
from .errors import APIError
from .practice import Practice, migrate as migrate_practice
from .staff_auth import migrate as migrate_staff, authenticate as staff_authenticate, require_staff

ROOT = Path(__file__).resolve().parent.parent
CATALOG = json.loads((ROOT / 'server/catalog.json').read_text())
MAX_BODY = 131072
ACTIVITY_QR_PREFIX = 'ochakovo:activity:v1:'


def now():
    return datetime.now(timezone.utc).isoformat()


def moscow_today():
    return datetime.now(timezone(timedelta(hours=3))).date()


def ident():
    return secrets.token_urlsafe(18)


def decode(value, fallback=None):
    try:
        return json.loads(value) if value else fallback
    except (TypeError, ValueError):
        return fallback


class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as db:
            db.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, profile TEXT);
            CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, user_id TEXT REFERENCES users(id), expires REAL);
            CREATE TABLE IF NOT EXISTS progress (user_id TEXT REFERENCES users(id), task TEXT, draft TEXT DEFAULT '{}', completed TEXT, draft_revision INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(user_id,task));
            CREATE TABLE IF NOT EXISTS ledger (id TEXT PRIMARY KEY, user_id TEXT REFERENCES users(id), reason TEXT, delta INTEGER, created TEXT, UNIQUE(user_id,reason));
            CREATE TABLE IF NOT EXISTS applications (id TEXT PRIMARY KEY, user_id TEXT REFERENCES users(id), offer TEXT, profile TEXT, status TEXT, created TEXT, UNIQUE(user_id,offer));
            CREATE TABLE IF NOT EXISTS registrations (id TEXT PRIMARY KEY, user_id TEXT REFERENCES users(id), event TEXT, status TEXT, created TEXT, UNIQUE(user_id,event));
            CREATE TABLE IF NOT EXISTS exchanges (id TEXT PRIMARY KEY, user_id TEXT REFERENCES users(id), reward TEXT, created TEXT, UNIQUE(user_id,reward));
            CREATE TABLE IF NOT EXISTS analytics (id INTEGER PRIMARY KEY, user_id TEXT REFERENCES users(id), event TEXT, created TEXT);
            CREATE TABLE IF NOT EXISTS event_activities (
                id TEXT PRIMARY KEY, event_id TEXT NOT NULL, title TEXT NOT NULL,
                description TEXT NOT NULL, points INTEGER NOT NULL CHECK(points BETWEEN 1 AND 1000),
                active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)), qr_token TEXT NOT NULL UNIQUE
            );
            CREATE TABLE IF NOT EXISTS activity_completions (
                user_id TEXT NOT NULL REFERENCES users(id),
                activity_id TEXT NOT NULL REFERENCES event_activities(id),
                completed_at TEXT NOT NULL, awarded_points INTEGER NOT NULL CHECK(awarded_points BETWEEN 1 AND 1000),
                PRIMARY KEY(user_id,activity_id)
            );
            CREATE INDEX IF NOT EXISTS idx_event_activities_event ON event_activities(event_id,active);
            CREATE INDEX IF NOT EXISTS idx_activity_completions_activity ON activity_completions(activity_id);
            CREATE INDEX IF NOT EXISTS idx_sessions_expiry ON sessions(expires);
            CREATE INDEX IF NOT EXISTS idx_registrations_event ON registrations(event,status);
            CREATE INDEX IF NOT EXISTS idx_exchanges_reward ON exchanges(reward);
            CREATE INDEX IF NOT EXISTS idx_ledger_user ON ledger(user_id);
            ''')
            # Upgrade existing installations in place; do not rebuild or drop progress.
            columns={row['name'] for row in db.execute('PRAGMA table_info(progress)')}
            if 'draft_revision' not in columns:
                db.execute('ALTER TABLE progress ADD COLUMN draft_revision INTEGER NOT NULL DEFAULT 0')
            migrate_practice(db)
            migrate_staff(db)
            # Seeds contain definitions only. Tokens live in the ignored database and
            # existing activity data and deactivations survive every application restart.
            db.commit()
            db.execute('BEGIN IMMEDIATE')
            for event in CATALOG['events']:
                for activity in event.get('activities',[]):
                    if not db.execute('SELECT 1 FROM event_activities WHERE id=?',(activity['id'],)).fetchone():
                        db.execute('INSERT INTO event_activities(id,event_id,title,description,points,active,qr_token) VALUES(?,?,?,?,?,?,?)',
                                   (activity['id'],event['id'],activity['title'],activity['description'],activity['points'],int(activity.get('active',True)),secrets.token_urlsafe(32)))
            db.commit()

    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        return db

    @contextmanager
    def transaction(self):
        db = self.connect()
        try:
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def balance(db, user_id):
        return db.execute('SELECT COALESCE(SUM(delta),0) FROM ledger WHERE user_id=?', (user_id,)).fetchone()[0]

    @staticmethod
    def activity(row):
        value={'id':row['id'],'eventId':row['event_id'],'title':row['title'],
               'description':row['description'],'points':row['points'],'active':bool(row['active'])}
        return value

    @staticmethod
    def activity_completions(db,uid):
        return [{'activityId':row['activity_id'],'eventId':row['event_id'],'completedAt':row['completed_at'],'awardedPoints':row['awarded_points']}
                for row in db.execute('SELECT c.activity_id,a.event_id,c.completed_at,c.awarded_points FROM activity_completions c JOIN event_activities a ON a.id=c.activity_id WHERE c.user_id=? ORDER BY c.completed_at,c.activity_id',(uid,))]

    @staticmethod
    def catalog(db):
        catalog = copy.deepcopy(CATALOG)
        for event in catalog['events']:
            count = db.execute("SELECT COUNT(*) FROM registrations WHERE event=? AND status='registered'", (event['id'],)).fetchone()[0]
            event['remaining'] = max(0,event['capacity']-count)
            event['activities']=[Store.activity(row) for row in db.execute('SELECT * FROM event_activities WHERE event_id=? ORDER BY rowid',(event['id'],))]
        for reward in catalog['rewards']:
            count=db.execute('SELECT COUNT(*) FROM exchanges WHERE reward=?',(reward['id'],)).fetchone()[0]
            reward['remaining']=max(0,reward['stock']-count)
        return catalog

    @staticmethod
    def rows(db, table, user_id):
        result=[dict(row) for row in db.execute(f'SELECT * FROM {table} WHERE user_id=?', (user_id,))]
        for row in result:
            row.pop('user_id',None)
            if table=='progress':
                row['draft']=decode(row['draft'],{})
                row['revision']=row.pop('draft_revision')
            if table=='applications': row['profile']=decode(row['profile'],{})
            if 'offer' in row: row['offerId']=row['offer']
            if 'event' in row: row['eventId']=row['event']
            if 'reward' in row: row['rewardId']=row['reward']
        return result

    def bootstrap(self, db, uid):
        profile=decode(db.execute('SELECT profile FROM users WHERE id=?',(uid,)).fetchone()[0])
        rows={table:self.rows(db,table,uid) for table in ('progress','applications','registrations','exchanges','ledger')}
        task_ids=['shift-1','signal-1','movement-1','lab-1','delivery-1','history-1']
        completed_ids=[task_id for task_id in task_ids if any(p['task']==task_id and p['completed'] for p in rows['progress'])]
        route_progress={'completed':len(completed_ids),'total':len(task_ids),'taskIds':task_ids,'completedTaskIds':completed_ids}
        return dict(user={'id':uid},profile=profile,balance=self.balance(db,uid),catalog=self.catalog(db),
                    routeCompleted=len(completed_ids)==len(task_ids),routeProgress=route_progress,activityCompletions=self.activity_completions(db,uid),**rows)


class API:
    def __init__(self, store, config=None):
        self.store=store
        self.config=dict(os.environ if config is None else config)
        self.practice=Practice(self.config)

    def vk_user(self, raw):
        secret=self.config.get('VK_APP_SECRET','')
        app_id=self.config.get('VK_APP_ID','')
        if not secret or not app_id:
            raise APIError(503,'VK-вход ещё не настроен. Укажите VK_APP_ID и VK_APP_SECRET на сервере.','vk_not_configured')
        if isinstance(raw,str):
            query=urlsplit(raw).query if '://' in raw else raw.lstrip('?')
            try: pairs=parse_qsl(query,keep_blank_values=True,max_num_fields=100)
            except ValueError: raise APIError(401,'Некорректные параметры запуска.','invalid_launch')
            if len({k for k,v in pairs})!=len(pairs):
                raise APIError(401,'Повторяющиеся параметры запуска.','invalid_launch')
            params=dict(pairs)
        elif isinstance(raw,dict) and all(isinstance(k,str) and isinstance(v,(str,int)) and not isinstance(v,bool) for k,v in raw.items()):
            params={k:str(v) for k,v in raw.items()}
        else:
            raise APIError(401,'Не переданы параметры запуска VK.','invalid_launch')
        query=urlencode(sorted((k,v) for k,v in params.items() if k.startswith('vk_')))
        expected=base64.urlsafe_b64encode(hmac.new(secret.encode(),query.encode(),hashlib.sha256).digest()).decode().rstrip('=')
        if not hmac.compare_digest(expected.encode(),params.get('sign','').encode()) or params.get('vk_app_id')!=str(app_id):
            raise APIError(401,'Не удалось проверить подпись VK.','invalid_launch')
        try:
            uid=int(params.get('vk_user_id','0'));stamp=int(params.get('vk_ts','0'))
        except (ValueError,TypeError):
            raise APIError(401,'Некорректные параметры VK.','invalid_launch')
        ttl=int(self.config.get('VK_LAUNCH_TTL','3600'))
        if uid<=0 or stamp>time.time()+60 or stamp<time.time()-ttl:
            raise APIError(401,'Ссылка запуска устарела. Откройте приложение заново из VK.','launch_expired')
        return 'vk:'+str(uid)

    def auth(self, body, peer, headers=None):
        if 'devUserId' in body:
            try: local=ipaddress.ip_address(peer).is_loopback
            except ValueError: local=False
            headers=headers or {}
            host=urlsplit('http://'+headers.get('Host','localhost')).hostname or ''
            local_host=host in ('localhost','127.0.0.1','::1')
            forwarded=any(headers.get(key) for key in ('Forwarded','X-Forwarded-For','X-Forwarded-Host','X-Real-IP'))
            if self.config.get('DEV_AUTH')!='1' or not local or not local_host or forwarded:
                raise APIError(403,'Демонстрационный вход разрешён только локально при DEV_AUTH=1.','dev_auth_disabled')
            raw=str(body['devUserId'])
            if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',raw):
                raise APIError(400,'Некорректный идентификатор демопользователя.')
            uid='demo:'+raw;mode='demo'
        else:
            uid=self.vk_user(body.get('launchParams'));mode='vk'
        token=secrets.token_urlsafe(32)
        # Only token hashes are persisted; a database read does not expose active credentials.
        with self.store.transaction() as db:
            db.execute('INSERT OR IGNORE INTO users(id) VALUES(?)',(uid,))
            db.execute('DELETE FROM sessions WHERE expires<?',(time.time(),))
            db.execute('INSERT INTO sessions VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),uid,time.time()+86400))
            db.execute('INSERT INTO analytics(user_id,event,created) VALUES(?,?,?)',(uid,'session_started',now()))
        return dict(token=token,userId=uid,mode=mode)

    def session(self, db, headers):
        auth=headers.get('Authorization','')
        token=auth[7:] if auth.startswith('Bearer ') else ''
        row=db.execute('SELECT user_id FROM sessions WHERE token=? AND expires>?',(hashlib.sha256(token.encode()).hexdigest(),time.time())).fetchone() if token else None
        if not row:
            raise APIError(401,'Войдите в приложение заново.','unauthorized')
        return row[0]

    @staticmethod
    def require_profile(db, uid):
        row=db.execute('SELECT profile FROM users WHERE id=?',(uid,)).fetchone()
        profile=decode(row[0]) if row else None
        if not profile or profile.get('consent') is not True:
            raise APIError(409,'Сначала заполните и сохраните профиль.','profile_required')
        return profile

    @staticmethod
    def item(group, item_id):
        item=next((x for x in CATALOG[group] if x['id']==item_id),None)
        if not item: raise APIError(404,'Объект не найден.','not_found')
        return item

    @staticmethod
    def profile(body):
        if not isinstance(body,dict): raise APIError(400,'Профиль должен быть объектом.')
        required=('fullName','contact','birthDate','direction','availability','education')
        errors={}
        for key in required:
            if not isinstance(body.get(key),str) or not body[key].strip(): errors[key]='Заполните поле.'
            elif len(body[key])>300: errors[key]='Не более 300 символов.'
        age_restricted=False
        if not errors.get('birthDate'):
            try:
                raw_birthday=body['birthDate']
                if not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}',raw_birthday): raise ValueError()
                birthday=date.fromisoformat(raw_birthday)
                today=moscow_today()
                if birthday.isoformat()!=raw_birthday or birthday>today: raise ValueError()
                age=today.year-birthday.year-((today.month,today.day)<(birthday.month,birthday.day))
                if age>100: raise ValueError()
                age_restricted=age<18
            except ValueError: errors['birthDate']='Укажите корректную дату рождения в формате ГГГГ-ММ-ДД, не позднее сегодняшней даты.'
        if not errors.get('fullName') and len(body['fullName'].strip().split())<2: errors['fullName']='Укажите имя и фамилию.'
        if not errors.get('contact'):
            contact=body['contact'].strip()
            email=re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',contact)
            phone=re.fullmatch(r'[+\d\s()\-]+',contact) and 10<=len(re.sub(r'\D','',contact))<=15
            if not email and not phone: errors['contact']='Укажите телефон или email.'
        if body.get('consent') is not True: errors['consent']='Нужно согласие на обработку данных.'
        for flag in ('futureContact',):
            if flag in body and type(body[flag]) is not bool: errors[flag]='Выберите да или нет.'
        if 'schedule' in body and (not isinstance(body['schedule'],str) or len(body['schedule'])>300): errors['schedule']='Не более 300 символов.'
        if age_restricted:
            message='Регистрация доступна с 18 лет. Возвращайтесь, когда вам исполнится 18.'
            raise APIError(422,message,'age_restricted',{'birthDate':message})
        if errors: raise APIError(422,'Проверьте заполнение профиля.','validation_error',errors)
        return {**{k:body[k].strip() for k in required},'schedule':body.get('schedule','').strip(),'consent':True,'futureContact':body.get('futureContact',False),'consentedAt':now()}

    def scan_activity(self, db, uid, body):
        code=body.get('code')
        match=re.fullmatch(re.escape(ACTIVITY_QR_PREFIX)+r'([A-Za-z0-9_-]{43})',code) if isinstance(code,str) else None
        if not match: raise APIError(400,'Этот QR-код не относится к активности приложения.','qr_invalid')
        row=db.execute('SELECT * FROM event_activities WHERE qr_token=?',(match[1],)).fetchone()
        if not row: raise APIError(404,'Активность по этому QR-коду не найдена.','activity_not_found')
        if not row['active']: raise APIError(409,'Эта активность сейчас недоступна.','activity_inactive')
        event=self.item('events',row['event_id'])
        existing=db.execute('SELECT completed_at,awarded_points FROM activity_completions WHERE user_id=? AND activity_id=?',(uid,row['id'])).fetchone()
        if existing:
            stamp=existing['completed_at'];points=0
        else:
            stamp=now();points=row['points']
            db.execute('INSERT INTO activity_completions(user_id,activity_id,completed_at,awarded_points) VALUES(?,?,?,?)',(uid,row['id'],stamp,points))
            db.execute('INSERT INTO ledger VALUES(?,?,?,?,?)',(ident(),uid,'event-activity:'+row['id'],points,stamp))
            db.execute('INSERT INTO analytics(user_id,event,created) VALUES(?,?,?)',(uid,'event_activity_completed',stamp))
        return {'activity':self.store.activity(row),'event':{'id':event['id'],'title':event['title']},
                'completion':{'activityId':row['id'],'eventId':row['event_id'],'completedAt':stamp,'awardedPoints':existing['awarded_points'] if existing else points},
                'pointsAwarded':points,'alreadyCompleted':existing is not None,'balance':self.store.balance(db,uid)}

    def dispatch(self, method, path, body=None, headers=None, peer='127.0.0.1'):
        headers=headers or {};body=body if body is not None else {}
        path=urlsplit(path).path.rstrip('/') or '/'
        if method=='GET' and path=='/api/health': return {'ok':True,'service':'ochakovo-api'}
        if method=='GET' and path=='/api/config':
            return {'devAuth':self.config.get('DEV_AUTH')=='1' and ipaddress.ip_address(peer).is_loopback,'vkConfigured':bool(self.config.get('VK_APP_SECRET') and self.config.get('VK_APP_ID'))}
        if method=='POST' and path=='/api/auth': return self.auth(body,peer,headers)
        if method=='POST' and path=='/api/staff/login':
            with self.store.transaction() as db:
                result, error = staff_authenticate(db,body,peer)
            if error: raise error
            return result
        with self.store.transaction() as db:
            if method=='GET' and path=='/api/catalog': return self.store.catalog(db)
            if path.startswith('/api/admin/'):
                return self.admin(db,method,path,body,headers)
            uid=self.session(db,headers)
            if method=='GET' and path=='/api/staff/session':
                return {'role': require_staff(db,uid), 'userId':uid}
            if method=='GET' and path=='/api/bootstrap':
                return {**self.store.bootstrap(db,uid), 'practiceAccess': self.practice.access(db,uid)}
            if path.startswith('/api/practice/'):
                require_staff(db,uid)
                return self.practice.dispatch(db,uid,method,path,body)
            if method=='GET' and path=='/api/profile':
                return {'profile':decode(db.execute('SELECT profile FROM users WHERE id=?',(uid,)).fetchone()[0])}
            if method=='PUT' and path=='/api/profile':
                profile=self.profile(body)
                db.execute('UPDATE users SET profile=? WHERE id=?',(json.dumps(profile,ensure_ascii=False),uid))
                db.execute('INSERT INTO analytics(user_id,event,created) VALUES(?,?,?)',(uid,'profile_saved',now()))
                return {'profile':profile}
            if method=='DELETE' and path=='/api/auth':
                token=headers.get('Authorization','')[7:]
                db.execute('DELETE FROM sessions WHERE token=?',(hashlib.sha256(token.encode()).hexdigest(),))
                return {'ok':True}
            if method=='GET' and path=='/api/ledger': return {'balance':self.store.balance(db,uid),'ledger':self.store.rows(db,'ledger',uid)}
            if method=='POST' and path=='/api/analytics':
                event=body.get('event','')
                allowed={'onboarding_started','profile_form_opened','offer_viewed','task_opened','task_started','task_hint','event_viewed','reward_viewed','application_reviewed'}
                if event not in allowed: raise APIError(400,'Неизвестное аналитическое событие.')
                db.execute('INSERT INTO analytics(user_id,event,created) VALUES(?,?,?)',(uid,event,now()))
                return {'ok':True}
            profile=self.require_profile(db,uid)
            if method=='POST' and path=='/api/event-activities/scan': return self.scan_activity(db,uid,body)
            match=re.fullmatch(r'/api/tasks/([^/]+)/(draft|complete)',path)
            if match:
                task=self.item('tasks',match[1]);action=match[2]
                if method=='PUT' and action=='draft':
                    draft=body.get('draft')
                    if not isinstance(draft,dict) or len(json.dumps(draft))>65536: raise APIError(400,'Некорректный черновик.')
                    if task['game']=='shift':
                        try: draft=normalize_shift_draft(task,draft)
                        except ValueError as error: raise APIError(400,str(error))
                        if len(json.dumps(draft))>65536: raise APIError(400,'Черновик слишком большой.')
                    existing=db.execute('SELECT draft,draft_revision FROM progress WHERE user_id=? AND task=?',(uid,task['id'])).fetchone()
                    stored_revision=existing['draft_revision'] if existing else 0
                    revision=body.get('revision')
                    if 'revision' in body:
                        if type(revision) is not int or not 0<=revision<=9007199254740991:
                            raise APIError(400,'Некорректная версия черновика.')
                    else:
                        # Legacy clients remain supported; new clients send a monotonic millisecond revision.
                        revision=max(time.time_ns()//1000000,stored_revision+1)
                    if revision<stored_revision:
                        return {'saved':False,'reason':'stale','draft':decode(existing['draft'],{}),'revision':stored_revision}
                    db.execute("INSERT INTO progress(user_id,task,draft,draft_revision) VALUES(?,?,?,?) ON CONFLICT(user_id,task) DO UPDATE SET draft=excluded.draft,draft_revision=excluded.draft_revision WHERE excluded.draft_revision>=progress.draft_revision",(uid,task['id'],json.dumps(draft,ensure_ascii=False),revision))
                    return {'saved':True,'revision':revision,'progress':self.store.rows(db,'progress',uid)}
                if method=='POST' and action=='complete':
                    if task['game']=='shift':
                        saved=db.execute('SELECT draft FROM progress WHERE user_id=? AND task=?',(uid,task['id'])).fetchone()
                        saved_draft=decode(saved['draft'],{}) if saved else {}
                        observation_ids=[item.get('factId') for item in saved_draft.get('observations',[]) if isinstance(item,dict)]
                        errors=assess_shift(task,body.get('solution'),observation_ids)
                    else:
                        errors=validate(task,body.get('solution'))
                    if errors: return {'correct':False,'errors':errors,'pointsAwarded':0,'alreadyCompleted':False}
                    previous=db.execute('SELECT completed FROM progress WHERE user_id=? AND task=?',(uid,task['id'])).fetchone()
                    completed=previous[0] if previous and previous[0] else now()
                    db.execute("INSERT INTO progress(user_id,task,draft,completed) VALUES(?,?,?,?) ON CONFLICT(user_id,task) DO UPDATE SET completed=COALESCE(progress.completed,excluded.completed)",(uid,task['id'],json.dumps(body['solution'],ensure_ascii=False),completed))
                    awarded=db.execute('INSERT OR IGNORE INTO ledger VALUES(?,?,?,?,?)',(ident(),uid,'task:'+task['id'],task['points'],now())).rowcount>0
                    db.execute('INSERT INTO analytics(user_id,event,created) VALUES(?,?,?)',(uid,'task_completed',now()))
                    return {'correct':True,'pointsAwarded':task['points'] if awarded else 0,'alreadyCompleted':not awarded,'balance':self.store.balance(db,uid),'progress':self.store.rows(db,'progress',uid),**(shift_completion_details(task) if task['game']=='shift' else {'explanation':task['explanation']})}
            if method=='POST' and path=='/api/applications':
                offer=self.item('offers',body.get('offerId'))
                application_id=ident()
                inserted=db.execute('INSERT OR IGNORE INTO applications VALUES(?,?,?,?,?,?)',(application_id,uid,offer['id'],json.dumps(profile,ensure_ascii=False),'sent',now())).rowcount>0
                if inserted: db.execute('INSERT INTO analytics(user_id,event,created) VALUES(?,?,?)',(uid,'application_sent',now()))
                row=dict(db.execute('SELECT * FROM applications WHERE user_id=? AND offer=?',(uid,offer['id'])).fetchone())
                row['profile']=decode(row['profile']);row['offerId']=row['offer'];row.pop('user_id')
                return {'application':row,'alreadyApplied':not inserted,'demo':True,'message':'Тестовый отклик принят сервером. Доступен в HR-кабинете демонстрации.'}
            match=re.fullmatch(r'/api/events/([^/]+)/registration',path)
            if match and method in ('POST','DELETE'):
                event=self.item('events',match[1]);existing=db.execute('SELECT * FROM registrations WHERE user_id=? AND event=?',(uid,event['id'])).fetchone()
                if method=='POST':
                    if existing and existing['status']=='registered': return {'registration':dict(existing),'alreadyRegistered':True}
                    if datetime.fromisoformat(event['date']+'T'+event['startTime']+'+03:00').timestamp()<=time.time(): raise APIError(409,'Запись на событие завершена.','event_closed')
                    occupied=db.execute("SELECT COUNT(*) FROM registrations WHERE event=? AND status='registered'",(event['id'],)).fetchone()[0]
                    if occupied>=event['capacity']: raise APIError(409,'Свободные места закончились.','event_full')
                    db.execute("INSERT INTO registrations VALUES(?,?,?,?,?) ON CONFLICT(user_id,event) DO UPDATE SET status='registered',created=excluded.created",(ident(),uid,event['id'],'registered',now()))
                    event_name='event_registered'
                else:
                    db.execute("UPDATE registrations SET status='cancelled' WHERE user_id=? AND event=?",(uid,event['id']))
                    event_name='event_cancelled'
                db.execute('INSERT INTO analytics(user_id,event,created) VALUES(?,?,?)',(uid,event_name,now()))
                row=db.execute('SELECT * FROM registrations WHERE user_id=? AND event=?',(uid,event['id'])).fetchone()
                return {'registration':dict(row) if row else None,'catalog':self.store.catalog(db)}
            match=re.fullmatch(r'/api/rewards/([^/]+)/exchange',path)
            if match and method=='POST':
                reward=self.item('rewards',match[1])
                existing=db.execute('SELECT * FROM exchanges WHERE user_id=? AND reward=?',(uid,reward['id'])).fetchone()
                if existing: return {'exchange':dict(existing),'alreadyExchanged':True,'balance':self.store.balance(db,uid)}
                count=db.execute('SELECT COUNT(*) FROM exchanges WHERE reward=?',(reward['id'],)).fetchone()[0]
                if count>=reward['stock']: raise APIError(409,'Награда закончилась.','reward_unavailable')
                if self.store.balance(db,uid)<reward['cost']: raise APIError(409,'Недостаточно баллов для обмена.','insufficient_points')
                exchange_id=ident();stamp=now()
                db.execute('INSERT INTO exchanges VALUES(?,?,?,?)',(exchange_id,uid,reward['id'],stamp))
                db.execute('INSERT INTO ledger VALUES(?,?,?,?,?)',(ident(),uid,'exchange:'+reward['id'],-reward['cost'],stamp))
                db.execute('INSERT INTO analytics(user_id,event,created) VALUES(?,?,?)',(uid,'reward_exchanged',stamp))
                return {'exchange':{'id':exchange_id,'reward':reward['id'],'rewardId':reward['id'],'created':stamp},'alreadyExchanged':False,'balance':self.store.balance(db,uid),'catalog':self.store.catalog(db)}
            raise APIError(404,'Маршрут не найден.','not_found')

    def admin(self, db, method, path, body, headers):
        expected=self.config.get('ADMIN_TOKEN','')
        provided=headers.get('X-Admin-Token','')
        if not provided and headers.get('Authorization','').startswith('Bearer '): provided=headers['Authorization'][7:]
        if not expected or not hmac.compare_digest(expected.encode(),provided.encode()): raise APIError(401,'Требуется токен HR-кабинета.','admin_unauthorized')
        if method=='GET' and path=='/api/admin/applications':
            applications=[]
            for row in db.execute('SELECT * FROM applications ORDER BY created DESC'):
                row=dict(row);row['profile']=decode(row['profile']);row['offerId']=row['offer'];row['userId']=row.pop('user_id');applications.append(row)
            return {'applications':applications,'demo':True}
        match=re.fullmatch(r'/api/admin/applications/([^/]+)',path)
        if match and method=='PATCH':
            status=body.get('status')
            if status not in ('sent','reviewing','contacted','accepted','rejected'): raise APIError(422,'Недопустимый статус.')
            if not db.execute('UPDATE applications SET status=? WHERE id=?',(status,match[1])).rowcount: raise APIError(404,'Отклик не найден.')
            return {'ok':True,'status':status}
        if method=='GET' and path=='/api/admin/analytics':
            return {'events':[dict(r) for r in db.execute('SELECT event,COUNT(*) AS count FROM analytics GROUP BY event')], 'profiles':db.execute('SELECT COUNT(*) FROM users WHERE profile IS NOT NULL').fetchone()[0],'applications':db.execute('SELECT COUNT(*) FROM applications').fetchone()[0]}
        raise APIError(404,'Маршрут не найден.','not_found')


class Handler(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def log_message(self, fmt, *args):
        # Never include launch queries, tokens, request bodies, or personal data in access logs.
        print('%s %s' % (self.command,urlsplit(self.path).path),flush=True)

    def send_json(self, status, value):
        payload=json.dumps(value,ensure_ascii=False).encode()
        self.send_response(status)
        if status>=400:
            self.send_header('Connection','close')
            self.close_connection=True
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(payload)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        origin=self.headers.get('Origin','')
        allowed=self.server.api.config.get('ALLOWED_ORIGINS','').split(',')
        if origin and origin in allowed:
            self.send_header('Access-Control-Allow-Origin',origin)
            self.send_header('Vary','Origin')
        self.end_headers()
        self.wfile.write(payload)

    def do_OPTIONS(self):
        origin=self.headers.get('Origin','')
        if origin not in self.server.api.config.get('ALLOWED_ORIGINS','').split(','):
            return self.send_json(403,{'error':'Origin is not allowed','code':'origin_forbidden'})
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin',origin)
        self.send_header('Access-Control-Allow-Headers','Authorization, Content-Type, X-Admin-Token')
        self.send_header('Access-Control-Allow-Methods','GET, POST, PUT, DELETE, PATCH, OPTIONS')
        self.send_header('Content-Length','0');self.end_headers()

    def serve_static(self):
        dist=Path(self.server.api.config.get('DIST_DIR',str(ROOT/'dist'))).resolve()
        route=unquote(urlsplit(self.path).path)
        parts=Path(route.lstrip('/')).parts
        if any(part.startswith('.') or part=='..' for part in parts) or '\\' in route:
            return self.send_json(404,{'error':'Файл не найден.','code':'not_found'})
        target=(dist/route.lstrip('/')).resolve()
        if not target.is_relative_to(dist):
            return self.send_json(404,{'error':'Файл не найден.','code':'not_found'})
        if target.is_dir(): target=target/'index.html'
        if not target.is_file():
            # Client routes may fall back to index; missing assets must remain 404.
            if not Path(route).suffix and (dist/'index.html').is_file(): target=dist/'index.html'
            else: return self.send_json(404,{'error':'Файл не найден. Выполните npm run build.','code':'not_found'})
        payload=target.read_bytes()
        mime=mimetypes.guess_type(target.name)[0] or 'application/octet-stream'
        self.send_response(200)
        self.send_header('Content-Type',mime+('; charset=utf-8' if mime.startswith('text/') or mime=='application/javascript' else ''))
        self.send_header('Content-Length',str(len(payload)))
        self.send_header('Cache-Control','no-cache' if target.name=='index.html' else 'public, max-age=31536000, immutable' if target.parent.name=='assets' else 'public, max-age=3600')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','strict-origin-when-cross-origin')
        self.end_headers()
        if self.command!='HEAD': self.wfile.write(payload)

    def handle_request(self):
        try:
            if not urlsplit(self.path).path.startswith('/api/'):
                if self.command in ('GET','HEAD'): return self.serve_static()
                raise APIError(405,'Метод не поддерживается.','method_not_allowed')
            origin=self.headers.get('Origin','')
            if origin and origin not in self.server.api.config.get('ALLOWED_ORIGINS','').split(','):
                # Same-origin production requests are permitted; hostname matches behind proxy via explicit config.
                own=f'http://{self.headers.get("Host", "")}'
                own_tls=f'https://{self.headers.get("Host", "")}'
                if origin not in (own,own_tls): raise APIError(403,'Источник запроса не разрешён.','origin_forbidden')
            raw_length=self.headers.get('Content-Length','0')
            try: length=int(raw_length)
            except ValueError: raise APIError(400,'Некорректная длина запроса.')
            if length<0 or length>MAX_BODY: raise APIError(413,'Запрос слишком большой.')
            body={}
            if length:
                if 'application/json' not in self.headers.get('Content-Type',''): raise APIError(415,'Используйте application/json.')
                try: body=json.loads(self.rfile.read(length))
                except (ValueError,UnicodeDecodeError): raise APIError(400,'Некорректный JSON.')
                if not isinstance(body,dict): raise APIError(400,'Тело запроса должно быть объектом.')
            result=self.server.api.dispatch(self.command,self.path,body,self.headers,self.client_address[0])
            self.send_json(200,result)
        except APIError as exc:
            error={'error':exc.message,'code':exc.code}
            if exc.details: error['details']=exc.details
            self.send_json(exc.status,error)
        except sqlite3.Error:
            self.send_json(503,{'error':'Хранилище временно недоступно. Повторите запрос.','code':'storage_unavailable'})
        except Exception:
            self.send_json(500,{'error':'Не удалось выполнить запрос.','code':'internal_error'})
    do_GET=do_HEAD=do_POST=do_PUT=do_DELETE=do_PATCH=handle_request


def create_server(host='127.0.0.1',port=3001,path=None,config=None):
    server=ThreadingHTTPServer((host,port),Handler)
    server.daemon_threads=True
    server.api=API(Store(path or ROOT/'.data/ochakovo.sqlite3'),config)
    return server
