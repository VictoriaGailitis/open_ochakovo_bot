"""Event QR activities: persistence, privacy, auth, and transactional rewards."""
import json
import secrets
import sqlite3
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from server.app import API, APIError, ACTIVITY_QR_PREFIX, CATALOG, Store, create_server


PROFILE={'fullName':'Тестовый участник','contact':'activity@example.org','birthDate':'2000-01-02','direction':'undecided','availability':'Пока знакомлюсь','education':'Учебный колледж','consent':True}


class ActivityTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)/'activities.db'
        self.config={'DEV_AUTH':'1','ADMIN_TOKEN':'activity-test-admin'}
        self.store=Store(self.path)
        self.api=API(self.store,self.config)
        self.admin={'X-Admin-Token':self.config['ADMIN_TOKEN']}
        self.headers=self.login('one')
        self.activity=self.activity_fixtures()[0]
    def tearDown(self):self.temp.cleanup()
    def login(self,uid,profile=True):
        result=self.api.auth({'devUserId':uid},'127.0.0.1')
        headers={'Authorization':'Bearer '+result['token']}
        if profile:self.api.dispatch('PUT','/api/profile',dict(PROFILE),headers)
        return headers
    def call(self,method,path,body=None,headers=None):return self.api.dispatch(method,path,body,headers or self.headers)
    def error(self,status,fn,code=None):
        with self.assertRaises(APIError) as caught:fn()
        self.assertEqual(caught.exception.status,status)
        if code:self.assertEqual(caught.exception.code,code)
    def scan(self,activity=None,headers=None,**extra):
        return self.call('POST','/api/event-activities/scan',{'code':(activity or self.activity)['code'],**extra},headers)
    def activity_fixtures(self):
        # QR payloads are read only from this test's temporary database.
        with closing(self.store.connect()) as db:
            return [{**Store.activity(row),'code':ACTIVITY_QR_PREFIX+row['qr_token']}
                    for row in db.execute('SELECT * FROM event_activities ORDER BY rowid')]
    def prepare_activity(self,fields,activity=None):
        # Fixture preparation, not a product management API or CLI.
        self.assertTrue(set(fields)<={'title','description','points','active'})
        activity_id=(activity or self.activity)['id']
        with self.store.transaction() as db:
            db.execute('UPDATE event_activities SET '+','.join(key+'=?' for key in fields)+' WHERE id=?',(*fields.values(),activity_id))
        return next(row for row in self.activity_fixtures() if row['id']==activity_id)

    def test_seeds_have_stable_private_codes_and_preserve_data_changes(self):
        original=self.activity_fixtures()
        ids={a['id'] for a in original}
        self.assertEqual(len(ids),len(original))
        self.assertEqual(len({a['code'] for a in original}),len(original))
        for event in CATALOG['events']:
            self.assertIn(sum(a['eventId']==event['id'] for a in original),(2,3))
        for activity in original:
            self.assertRegex(activity['code'],r'^ochakovo:activity:v1:[A-Za-z0-9_-]{43}$')
        changed=self.prepare_activity({'title':'Новое название','points':42,'active':False})
        self.api=API(Store(self.path),self.config)
        reopened=self.activity_fixtures()
        self.assertEqual({a['id']:a['code'] for a in original},{a['id']:a['code'] for a in reopened})
        persisted=next(a for a in reopened if a['id']==changed['id'])
        self.assertEqual((persisted['title'],persisted['points'],persisted['active']),('Новое название',42,False))

    def test_additive_migration_preserves_legacy_data_and_tokens(self):
        legacy_path=Path(self.temp.name)/'legacy.db'
        with closing(sqlite3.connect(legacy_path)) as db:
            db.executescript("""
                CREATE TABLE users (id TEXT PRIMARY KEY, profile TEXT);
                CREATE TABLE progress (user_id TEXT REFERENCES users(id),task TEXT,draft TEXT DEFAULT '{}',completed TEXT,PRIMARY KEY(user_id,task));
                CREATE TABLE ledger (id TEXT PRIMARY KEY,user_id TEXT REFERENCES users(id),reason TEXT,delta INTEGER,created TEXT,UNIQUE(user_id,reason));
                INSERT INTO users VALUES ('demo:legacy','{"consent":true}');
                INSERT INTO progress VALUES ('demo:legacy','signal-1','{"step":2}','2026-10-24T12:00:00Z');
                INSERT INTO ledger VALUES ('legacy-ledger','demo:legacy','task:signal-1',50,'2026-10-24T12:00:00Z');
            """)
            db.commit()
        migrated=Store(legacy_path)
        with closing(migrated.connect()) as db:
            self.assertEqual(db.execute('SELECT delta FROM ledger').fetchone()[0],50)
            progress=dict(db.execute('SELECT * FROM progress').fetchone())
            self.assertEqual(json.loads(progress['draft']),{'step':2})
            self.assertTrue(progress['completed'])
            tokens={r['id']:r['qr_token'] for r in db.execute('SELECT id,qr_token FROM event_activities')}
            self.assertTrue(tokens)
        reopened=Store(legacy_path)
        with closing(reopened.connect()) as db:
            self.assertEqual(tokens,{r['id']:r['qr_token'] for r in db.execute('SELECT id,qr_token FROM event_activities')})
            self.assertEqual(db.execute('SELECT COUNT(*) FROM activity_completions').fetchone()[0],0)

    def test_public_catalog_and_bootstrap_never_expose_scan_credentials(self):
        private_fixtures=self.activity_fixtures()
        catalog=self.call('GET','/api/catalog')
        bootstrap=self.call('GET','/api/bootstrap')
        self.assertEqual(bootstrap['activityCompletions'],[])
        serialized=json.dumps([catalog,bootstrap])
        for activity in private_fixtures:
            self.assertNotIn(activity['code'],serialized)
            self.assertNotIn(activity['code'][len(ACTIVITY_QR_PREFIX):],serialized)
        for event in catalog['events']:
            for activity in event['activities']:
                self.assertEqual(set(activity),{'id','eventId','title','description','points','active'})
                self.assertIs(type(activity['active']),bool)
        self.assertNotIn('qr_token',serialized)
        self.assertNotIn(ACTIVITY_QR_PREFIX,json.dumps(CATALOG))

    def test_scan_requires_profile_and_distinguishes_invalid_unknown_inactive(self):
        unregistered=self.login('without-profile',False)
        self.error(409,lambda:self.scan(headers=unregistered),'profile_required')
        self.error(401,lambda:self.api.dispatch('POST','/api/event-activities/scan',{'code':self.activity['code']},{}),'unauthorized')
        invalid=(None,'','https://example.org/qr','foreign:activity:v1:'+secrets.token_urlsafe(32),ACTIVITY_QR_PREFIX+'short',{'code':'not-string'})
        for code in invalid:
            self.error(400,lambda:self.call('POST','/api/event-activities/scan',{'code':code}),'qr_invalid')
        self.error(404,lambda:self.call('POST','/api/event-activities/scan',{'code':ACTIVITY_QR_PREFIX+secrets.token_urlsafe(32)}),'activity_not_found')
        inactive=self.prepare_activity({'active':False})
        self.error(409,lambda:self.scan(inactive),'activity_inactive')
        self.assertEqual(self.call('GET','/api/bootstrap')['activityCompletions'],[])
        self.assertEqual(self.call('GET','/api/ledger')['balance'],0)

    def test_walk_in_scan_does_not_register_or_consume_seats(self):
        before=self.call('GET','/api/bootstrap')
        result=self.scan(points=999999)
        after=self.call('GET','/api/bootstrap')
        self.assertEqual(result['pointsAwarded'],self.activity['points'])
        self.assertFalse(result['alreadyCompleted'])
        self.assertEqual(result['event']['id'],self.activity['eventId'])
        self.assertEqual(result['completion']['eventId'],self.activity['eventId'])
        self.assertEqual(result['balance'],self.activity['points'])
        self.assertEqual(before['registrations'],after['registrations'])
        self.assertEqual([e['remaining'] for e in before['catalog']['events']],[e['remaining'] for e in after['catalog']['events']])
        self.assertEqual(len(after['ledger']),1)
        self.assertEqual(after['ledger'][0]['reason'],'event-activity:'+self.activity['id'])
        self.assertEqual(after['activityCompletions'],[result['completion']])
        self.assertNotIn('code',result['activity'])

    def test_repeat_and_concurrent_scans_award_exactly_once(self):
        with ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(lambda _:self.scan(),range(16)))
        self.assertEqual(sum(r['pointsAwarded'] for r in results),self.activity['points'])
        self.assertEqual(sum(not r['alreadyCompleted'] for r in results),1)
        self.assertEqual(len({r['completion']['completedAt'] for r in results}),1)
        boot=self.call('GET','/api/bootstrap')
        self.assertEqual(len(boot['activityCompletions']),1)
        self.assertEqual(len(boot['ledger']),1)
        with closing(self.store.connect()) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM activity_completions WHERE activity_id=?',(self.activity['id'],)).fetchone()[0],1)

    def test_completion_ledger_and_balance_survive_restart_and_are_user_scoped(self):
        first=self.scan()
        other=self.login('other')
        self.assertEqual(self.call('GET','/api/bootstrap',headers=other)['activityCompletions'],[])
        second=self.scan(headers=other)
        self.assertFalse(second['alreadyCompleted'])
        self.assertEqual(second['pointsAwarded'],self.activity['points'])
        self.api=API(Store(self.path),self.config)
        self.assertEqual(self.call('GET','/api/bootstrap')['activityCompletions'],[first['completion']])
        self.assertEqual(self.call('GET','/api/ledger')['balance'],self.activity['points'])
        self.assertEqual(self.scan()['pointsAwarded'],0)
        with closing(self.store.connect()) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM activity_completions WHERE activity_id=?',(self.activity['id'],)).fetchone()[0],2)

    def test_editing_points_keeps_earned_amount_and_immutable_qr(self):
        first=self.scan()
        updated=self.prepare_activity({'points':77,'description':'Новое описание'})
        self.assertEqual(updated['code'],self.activity['code'])
        repeated=self.scan(updated)
        self.assertEqual(repeated['pointsAwarded'],0)
        self.assertEqual(repeated['balance'],self.activity['points'])
        self.assertEqual(repeated['completion'],first['completion'])
        self.assertEqual(repeated['completion']['awardedPoints'],self.activity['points'])
        self.assertEqual(self.call('GET','/api/bootstrap')['activityCompletions'][0]['awardedPoints'],self.activity['points'])
        other=self.login('new-after-edit')
        new_completion=self.scan(updated,other)
        self.assertEqual(new_completion['pointsAwarded'],77)
        self.assertEqual(new_completion['completion']['awardedPoints'],77)
        with closing(self.store.connect()) as db:
            old=db.execute('SELECT awarded_points FROM activity_completions WHERE user_id=? AND activity_id=?',('demo:one',self.activity['id'])).fetchone()[0]
            self.assertEqual(old,self.activity['points'])
        disabled=self.prepare_activity({'active':False})
        self.error(409,lambda:self.scan(disabled),'activity_inactive')
        enabled=self.prepare_activity({'active':True})
        self.assertEqual(enabled['code'],self.activity['code'])
        self.assertEqual(self.scan(enabled)['pointsAwarded'],0)

    def test_organizer_management_is_not_exposed_and_hr_is_unchanged(self):
        for method,path,body in [('GET','/api/admin/event-activities',None),
                                 ('POST','/api/admin/event-activities',{'eventId':'event-1','title':'Hidden','description':'Hidden','points':10}),
                                 ('PATCH','/api/admin/event-activities/'+self.activity['id'],{'active':False})]:
            self.error(404,lambda:self.call(method,path,body,self.admin),'not_found')
        self.assertEqual(self.call('GET','/api/admin/applications',headers=self.admin),{'applications':[],'demo':True})
        self.assertTrue(self.activity_fixtures()[0]['active'])

    def test_completion_and_ledger_are_one_atomic_transaction(self):
        with self.store.transaction() as db:
            db.execute("CREATE TRIGGER reject_activity_ledger BEFORE INSERT ON ledger WHEN NEW.reason LIKE 'event-activity:%' BEGIN SELECT RAISE(ABORT,'test ledger failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):self.scan()
        boot=self.call('GET','/api/bootstrap')
        self.assertEqual(boot['activityCompletions'],[])
        self.assertEqual(boot['ledger'],[])
        self.assertEqual(boot['balance'],0)
        with self.store.transaction() as db:db.execute('DROP TRIGGER reject_activity_ledger')
        self.assertEqual(self.scan()['pointsAwarded'],self.activity['points'])


class ActivityHTTPTest(unittest.TestCase):
    def test_http_public_scan_contract(self):
        with tempfile.TemporaryDirectory() as temp:
            server=create_server('127.0.0.1',0,Path(temp)/'http.db',{'DEV_AUTH':'1','ADMIN_TOKEN':'http-activity-test-admin'})
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            base=f'http://127.0.0.1:{server.server_port}'
            def request(path,method='GET',body=None,headers=None):
                req=Request(base+path,data=None if body is None else json.dumps(body).encode(),method=method,headers={'Content-Type':'application/json',**(headers or {})})
                try:
                    with urlopen(req,timeout=5) as response:return response.status,json.load(response)
                except HTTPError as error:return error.code,json.load(error)
            try:
                self.assertEqual(request('/api/admin/event-activities',headers={'X-Admin-Token':'http-activity-test-admin'})[0],404)
                with closing(server.api.store.connect()) as db:
                    fixture=db.execute('SELECT * FROM event_activities ORDER BY rowid LIMIT 1').fetchone()
                    activity={**Store.activity(fixture),'code':ACTIVITY_QR_PREFIX+fixture['qr_token']}
                _,auth=request('/api/auth','POST',{'devUserId':'http-scanner'})
                headers={'Authorization':'Bearer '+auth['token']}
                self.assertEqual(request('/api/event-activities/scan','POST',{'code':activity['code']},headers)[1]['code'],'profile_required')
                self.assertEqual(request('/api/profile','PUT',PROFILE,headers)[0],200)
                status,result=request('/api/event-activities/scan','POST',{'code':activity['code']},headers)
                self.assertEqual(status,200)
                self.assertEqual(result['pointsAwarded'],activity['points'])
                self.assertEqual(set(result),{'activity','event','completion','pointsAwarded','alreadyCompleted','balance'})
                self.assertEqual(request('/api/event-activities/scan','POST',{'code':activity['code']},headers)[1]['pointsAwarded'],0)
                self.assertEqual(request('/api/event-activities/scan','POST',{'code':'foreign'},headers)[1]['code'],'qr_invalid')
                _,boot=request('/api/bootstrap',headers=headers)
                self.assertEqual(boot['activityCompletions'],[result['completion']])
                self.assertNotIn(activity['code'],json.dumps(boot))
            finally:server.shutdown();server.server_close();thread.join()


if __name__=='__main__':unittest.main()
