import base64
import copy
import hashlib
import hmac
import json
import sqlite3
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from server.app import API, APIError, CATALOG, Store, create_server
from server.solutions import validate


PROFILE={'fullName':'Тестовый кандидат','contact':'test@example.org','birthDate':'2004-01-02','direction':'lab','availability':'С ноября','education':'Учебный колледж','schedule':'После учёбы','consent':True,'futureContact':False}


def solution(task):
    p=task['puzzle'];game=task['game']
    if game=='signal':
        cond={'color':'red','mark':'marked','combined':'red_marked'}[p['rule']]
        return {'rules':[{'condition':cond,'output':'left'},{'condition':'always','output':'right'}]}
    if game=='movement':
        target=p['target'];cells=[{'x':x,'y':1} for x in range(1,target['x']+1)]
        if target['y']==1: cells.pop()
        return {'gears':cells}
    if game=='lab':
        sample=next(x for x in p['samples'] if x['properties']==p['observations'])
        return {'sampleId':sample['id'],'evidence':['color','acidity']}
    if game=='delivery':
        products={o['product'] for o in p['order']}
        batches=[b for b in p['batches'] if not b['reserved'] and b['product'] in products]
        positions={'a':(0,0),'b':(2,0),'d':(3,0)}
        placements=[dict(batchId=b['id'],x=positions[b['id']][0],y=positions[b['id']][1],rotated=False) for b in batches]
        # Route walks past all possible collection locations.
        route=[{'x':x,'y':y} for x,y in [(0,0),(1,0),(2,0),(2,1),(1,1),(1,2),(1,3)]]
        return {'placements':placements,'route':route}
    return {'answers':{'founded':'1978','event':'olympics','brand':'secret'}}


class APITest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)/'app.db'
        self.store=Store(self.path)
        self.api=API(self.store,{'DEV_AUTH':'1','ADMIN_TOKEN':'test-admin','VK_APP_ID':'123','VK_APP_SECRET':'test-secret'})
        self.headers=self.login('one')
    def tearDown(self): self.temp.cleanup()
    def login(self,user,profile=True):
        auth=self.api.dispatch('POST','/api/auth',{'devUserId':user})
        headers={'Authorization':'Bearer '+auth['token']}
        if profile: self.api.dispatch('PUT','/api/profile',copy.deepcopy(PROFILE),headers)
        return headers
    def call(self,method,path,body=None,headers=None):
        return self.api.dispatch(method,path,body,headers or self.headers)
    def assert_error(self,status,fn):
        with self.assertRaises(APIError) as cm:fn()
        self.assertEqual(cm.exception.status,status)
        return cm.exception
    def complete(self,task_id='signal-1',headers=None):
        task=next(x for x in CATALOG['tasks'] if x['id']==task_id)
        return self.call('POST',f'/api/tasks/{task_id}/complete',{'solution':solution(task)},headers)

    def test_all_levels_have_valid_solutions(self):
        for task in CATALOG['tasks']:
            with self.subTest(task=task['id']):
                self.assertEqual(validate(task,solution(task)),[])
                result=self.complete(task['id'])
                self.assertTrue(result['correct'])
                self.assertEqual(result['pointsAwarded'],task['points'])
        boot=self.call('GET','/api/bootstrap')
        self.assertEqual(len(boot['progress']),13)
        self.assertEqual(boot['balance'],sum(x['points'] for x in CATALOG['tasks']))
        self.assertTrue(all(x['completed'] for x in boot['progress']))
        self.assertTrue(boot['routeCompleted'])
        self.assertEqual(boot['routeProgress']['completed'],5)

    def test_profile_and_game_gate(self):
        headers=self.login('new',False)
        self.assertIsNone(self.call('GET','/api/bootstrap',headers=headers)['profile'])
        self.assert_error(409,lambda:self.complete(headers=headers))
        self.assert_error(409,lambda:self.call('POST','/api/applications',{'offerId':'lab'},headers))
        self.assert_error(422,lambda:self.call('PUT','/api/profile',{**PROFILE,'consent':False},headers))
        self.assert_error(422,lambda:self.call('PUT','/api/profile',{**PROFILE,'contact':'wrong'},headers))
        self.assert_error(422,lambda:self.call('PUT','/api/profile',{**PROFILE,'birthDate':'2027-01-01'},headers))
        self.call('PUT','/api/profile',{**PROFILE,'contact':'+7 (999) 123-45-67'},headers)
        self.assertTrue(self.complete(headers=headers)['correct'])

    def test_draft_persistence_and_user_isolation(self):
        draft={'rules':[{'condition':'red','output':'left'}],'step':2}
        self.call('PUT','/api/tasks/signal-1/draft',{'draft':draft})
        # Reopen storage and sign in again to prove this is not in-memory state.
        api=API(Store(self.path),{'DEV_AUTH':'1'})
        token=api.auth({'devUserId':'one'},'127.0.0.1')['token']
        restored=api.dispatch('GET','/api/bootstrap',headers={'Authorization':'Bearer '+token})
        self.assertEqual(restored['progress'][0]['draft'],draft)
        other=self.login('other')
        self.assertEqual(self.call('GET','/api/bootstrap',headers=other)['progress'],[])

    def test_stale_draft_revision_cannot_overwrite_newer_state(self):
        newer={'gears':[{'x':1,'y':1},{'x':2,'y':1}]}
        older={'gears':[{'x':1,'y':1}]}
        saved=self.call('PUT','/api/tasks/movement-1/draft',{'draft':newer,'revision':200})
        self.assertTrue(saved['saved'])
        stale=self.call('PUT','/api/tasks/movement-1/draft',{'draft':older,'revision':100})
        self.assertFalse(stale['saved'])
        self.assertEqual(stale['reason'],'stale')
        self.assertEqual(stale['draft'],newer)
        self.assertEqual(stale['revision'],200)
        progress=self.call('GET','/api/bootstrap')['progress'][0]
        self.assertEqual(progress['draft'],newer)
        self.assertEqual(progress['revision'],200)
        # Concurrent out-of-order autosaves must converge to the highest revision.
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda revision:self.call('PUT','/api/tasks/movement-1/draft',{'draft':{'step':revision},'revision':revision}),[204,201,209,202,205,208,203,207,206]))
        progress=self.call('GET','/api/bootstrap')['progress'][0]
        self.assertEqual(progress['draft'],{'step':209})
        self.assertEqual(progress['revision'],209)
        # Completing a task and later saving cannot reset completion or its revision.
        self.complete('movement-1')
        self.assertEqual(self.call('GET','/api/bootstrap')['progress'][0]['revision'],209)
        result=self.call('PUT','/api/tasks/movement-1/draft',{'draft':newer})
        self.assertGreater(result['revision'],209)
        self.assertTrue(result['progress'][0]['completed'])
        for revision in (-1,True,1.5,'300',None,9007199254740992):
            self.assert_error(400,lambda:self.call('PUT','/api/tasks/movement-1/draft',{'draft':older,'revision':revision}))

    def test_legacy_progress_schema_is_migrated_without_data_loss(self):
        legacy_path=Path(self.temp.name)/'legacy.db'
        with closing(sqlite3.connect(legacy_path)) as db:
            db.executescript("""
                CREATE TABLE users (id TEXT PRIMARY KEY, profile TEXT);
                CREATE TABLE progress (user_id TEXT REFERENCES users(id), task TEXT, draft TEXT DEFAULT '{}', completed TEXT, PRIMARY KEY(user_id,task));
                INSERT INTO users VALUES ('demo:legacy',NULL);
                INSERT INTO progress VALUES ('demo:legacy','signal-1','{"rules":[]}',NULL);
            """)
            db.commit()
        migrated=Store(legacy_path)
        with closing(migrated.connect()) as db:
            row=dict(db.execute('SELECT * FROM progress').fetchone())
            self.assertEqual(row['draft_revision'],0)
            self.assertEqual(json.loads(row['draft']),{'rules':[]})
            self.assertIsNone(row['completed'])
            self.assertEqual(Store.rows(db,'progress','demo:legacy')[0]['revision'],0)
        # Migration is idempotent and a subsequently saved revision survives reopening.
        Store(legacy_path)
        with migrated.transaction() as db:
            db.execute('UPDATE progress SET draft_revision=123')
        reopened=Store(legacy_path)
        with closing(reopened.connect()) as db:
            self.assertEqual(db.execute('SELECT draft_revision FROM progress').fetchone()[0],123)

    def test_invalid_games_do_not_award(self):
        invalid={
            'signal-1':{'rules':[{'condition':'always','output':'left'}]},
            'movement-1':{'gears':[{'x':1,'y':1}]},
            'lab-1':{'sampleId':'b','evidence':['color']},
            'delivery-1':{'placements':[{'batchId':'c','x':0,'y':0}],'route':[{'x':0,'y':0}]},
            'history-1':{'answers':{'founded':'1980','event':'olympics','brand':'secret'}}}
        for task_id,attempt in invalid.items():
            result=self.call('POST',f'/api/tasks/{task_id}/complete',{'solution':attempt})
            self.assertFalse(result['correct'])
            self.assertTrue(result['errors'])
        self.assertEqual(self.call('GET','/api/ledger')['balance'],0)

    def test_signal_checks_unseen_inputs(self):
        task=copy.deepcopy(CATALOG['tasks'][0]);task['puzzle']['stream']=[{'color':'red','marked':True}]
        self.assertTrue(validate(task,{'rules':[{'condition':'always','output':'left'}]}))

    def test_movement_rejects_duplicates_and_detached_gear(self):
        task=next(t for t in CATALOG['tasks'] if t['id']=='movement-1')
        attempt=solution(task)
        attempt['gears'].append({'x':0,'y':1})
        self.assertTrue(validate(task,attempt))
        attempt=solution(task);attempt['gears'].append({'x':4,'y':0});attempt['gears'].append({'x':0,'y':0})
        # All are joined here; a truly detached gear is below the route with a gap.
        attempt=solution(task);attempt['gears'].append({'x':4,'y':2})
        self.assertFalse(validate(task,attempt))
        attempt=solution(task);attempt['gears'].append({'x':0,'y':-1})
        self.assertTrue(validate(task,attempt))

    def test_delivery_checks_overlap_route_and_reserved(self):
        task=next(t for t in CATALOG['tasks'] if t['id']=='delivery-1')
        attempt=solution(task);attempt['placements'][1]['x']=0
        self.assertTrue(validate(task,attempt))
        attempt=solution(task);attempt['route']=[{'x':0,'y':0},{'x':2,'y':1}]
        self.assertTrue(validate(task,attempt))
        attempt=solution(task);attempt['placements'][0]['batchId']='c'
        self.assertTrue(validate(task,attempt))

    def test_concurrent_completion_is_paid_once(self):
        with ThreadPoolExecutor(max_workers=8) as pool: results=list(pool.map(lambda _:self.complete(),range(12)))
        self.assertEqual(sum(x['pointsAwarded'] for x in results),50)
        self.assertEqual(sum(not x['alreadyCompleted'] for x in results),1)
        ledger=self.call('GET','/api/ledger')
        self.assertEqual(ledger['balance'],50)
        self.assertEqual(len(ledger['ledger']),1)
        # Draft updates cannot clear completion, nor allow another award.
        self.call('PUT','/api/tasks/signal-1/draft',{'draft':{'rules':[]}})
        self.assertTrue(self.complete()['alreadyCompleted'])
        self.assertTrue(self.call('GET','/api/bootstrap')['progress'][0]['completed'])

    def test_application_snapshot_idempotency_and_hr(self):
        result=self.call('POST','/api/applications',{'offerId':'lab'})
        app=result['application']
        self.assertEqual(app['status'],'sent')
        self.assertFalse(result['alreadyApplied'])
        self.assertTrue(self.call('POST','/api/applications',{'offerId':'lab'})['alreadyApplied'])
        self.assertEqual(self.call('GET','/api/ledger')['balance'],0)
        self.call('PUT','/api/profile',{**PROFILE,'fullName':'Новое имя'})
        self.assertEqual(self.call('GET','/api/bootstrap')['applications'][0]['profile']['fullName'],PROFILE['fullName'])
        self.assert_error(401,lambda:self.call('GET','/api/admin/applications'))
        admin={'X-Admin-Token':'test-admin'}
        self.call('PATCH','/api/admin/applications/'+app['id'],{'status':'reviewing'},admin)
        self.assertEqual(self.call('GET','/api/bootstrap')['applications'][0]['status'],'reviewing')
        self.assertEqual(len(self.call('GET','/api/admin/applications',headers=admin)['applications']),1)
        self.assert_error(422,lambda:self.call('PATCH','/api/admin/applications/'+app['id'],{'status':'made_up'},admin))

    def test_event_capacity_cancel_and_reregister(self):
        event=CATALOG['events'][0]
        users=[self.login('event-user-'+str(i)) for i in range(event['capacity']+2)]
        with ThreadPoolExecutor(max_workers=8) as pool:
            def register(headers):
                try: return self.call('POST','/api/events/'+event['id']+'/registration',headers=headers)
                except APIError as error: return error.code
            results=list(pool.map(register,users))
        self.assertEqual(sum(isinstance(x,dict) for x in results),event['capacity'])
        self.assertEqual(results.count('event_full'),2)
        self.assertEqual(self.call('GET','/api/catalog')['events'][0]['remaining'],0)
        winner=next(users[i] for i,r in enumerate(results) if isinstance(r,dict))
        loser=next(users[i] for i,r in enumerate(results) if r=='event_full')
        self.assertTrue(self.call('POST','/api/events/'+event['id']+'/registration',headers=winner)['alreadyRegistered'])
        self.call('DELETE','/api/events/'+event['id']+'/registration',headers=winner)
        self.assertEqual(self.call('GET','/api/catalog')['events'][0]['remaining'],1)
        self.call('POST','/api/events/'+event['id']+'/registration',headers=loser)
        self.assertEqual(self.call('GET','/api/catalog')['events'][0]['remaining'],0)

    def test_exchange_balance_stock_and_idempotency(self):
        self.assert_error(409,lambda:self.call('POST','/api/rewards/reward-1/exchange'))
        self.complete()
        with ThreadPoolExecutor(max_workers=6) as pool: results=list(pool.map(lambda _:self.call('POST','/api/rewards/reward-1/exchange'),range(8)))
        self.assertEqual(sum(not r['alreadyExchanged'] for r in results),1)
        boot=self.call('GET','/api/bootstrap')
        self.assertEqual(boot['balance'],0)
        self.assertEqual(len(boot['exchanges']),1)
        self.assertEqual(len(boot['ledger']),2)
        self.assertEqual(boot['catalog']['rewards'][0]['remaining'],CATALOG['rewards'][0]['stock']-1)

    def test_dev_auth_explicit_and_loopback_only(self):
        for config,peer in [({},'127.0.0.1'),({'DEV_AUTH':'1'},'10.0.0.2')]:
            api=API(self.store,config)
            self.assert_error(403,lambda:api.auth({'devUserId':'one'},peer))
        self.assert_error(400,lambda:self.api.auth({'devUserId':'bad user'},'127.0.0.1'))
        self.assert_error(403,lambda:self.api.auth({'devUserId':'one'},'127.0.0.1',{'Host':'evil.example'}))
        self.assert_error(403,lambda:self.api.auth({'devUserId':'one'},'127.0.0.1',{'Host':'localhost:3001','X-Forwarded-For':'203.0.113.1'}))
        self.assert_error(401,lambda:self.api.dispatch('GET','/api/bootstrap',headers={'Authorization':'Bearer invented'}))
        self.call('DELETE','/api/auth')
        self.assert_error(401,lambda:self.call('GET','/api/bootstrap'))

    def signed_launch(self,**changes):
        params={'vk_app_id':'123','vk_user_id':'777','vk_ts':str(int(time.time())),'vk_language':'ru'}
        params.update(changes)
        sign=base64.urlsafe_b64encode(hmac.new(b'test-secret',urlencode(sorted(params.items())).encode(),hashlib.sha256).digest()).decode().rstrip('=')
        return urlencode({**params,'sign':sign})

    def test_vk_hmac_app_timestamp_tamper(self):
        raw=self.signed_launch()
        self.assertEqual(self.api.auth({'launchParams':raw},'203.0.113.1')['userId'],'vk:777')
        self.assert_error(401,lambda:self.api.auth({'launchParams':raw.replace('777','778')},'127.0.0.1'))
        self.assert_error(401,lambda:self.api.auth({'launchParams':self.signed_launch(vk_app_id='999')},'127.0.0.1'))
        self.assert_error(401,lambda:self.api.auth({'launchParams':self.signed_launch(vk_ts='1')},'127.0.0.1'))
        self.assert_error(401,lambda:self.api.auth({'launchParams':self.signed_launch(vk_ts=str(int(time.time())+120))},'127.0.0.1'))
        self.assert_error(401,lambda:self.api.auth({'launchParams':raw+'&vk_user_id=777'},'127.0.0.1'))
        self.assert_error(503,lambda:API(self.store,{}).auth({'launchParams':raw},'127.0.0.1'))
        with closing(self.store.connect()) as db:
            stored=db.execute('SELECT token FROM sessions').fetchone()[0]
        self.assertEqual(len(stored),64)


class HTTPTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        cls.dist=Path(cls.temp.name)/'dist';cls.dist.mkdir()
        (cls.dist/'index.html').write_text('<html>Ochakovo app</html>')
        (cls.dist/'assets').mkdir();(cls.dist/'assets'/'app-test.js').write_text('console.log(1)')
        cls.server=create_server('127.0.0.1',0,Path(cls.temp.name)/'http.db',{'DEV_AUTH':'1','ALLOWED_ORIGINS':'http://localhost:5173','DIST_DIR':str(cls.dist)})
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.base=f'http://127.0.0.1:{cls.server.server_port}'
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join();cls.temp.cleanup()
    def request(self,path,method='GET',body=None,headers=None):
        headers={'Content-Type':'application/json',**(headers or {})}
        request=Request(self.base+path,data=None if body is None else json.dumps(body).encode(),method=method,headers=headers)
        try:
            with urlopen(request,timeout=5) as response:return response.status,json.load(response)
        except HTTPError as error:return error.code,json.load(error)
    def test_static_serving_confined_to_dist(self):
        for path in ('/','/career/lab'):
            with urlopen(self.base+path) as response:
                self.assertEqual(response.status,200)
                self.assertIn(b'Ochakovo app',response.read())
        with urlopen(self.base+'/assets/app-test.js') as response:
            self.assertIn('immutable',response.headers['Cache-Control'])
            self.assertIn('javascript',response.headers['Content-Type'])
        for path in ('/.data/admin-token','/%2e%2e/http.db','/assets/missing.js','/server/catalog.json'):
            self.assertEqual(self.request(path)[0],404)
        request=Request(self.base+'/',method='HEAD')
        with urlopen(request) as response:
            self.assertEqual(response.status,200)
            self.assertEqual(response.read(),b'')

    def test_http_end_to_end(self):
        status,auth=self.request('/api/auth','POST',{'devUserId':'http-user'})
        self.assertEqual(status,200)
        headers={'Authorization':'Bearer '+auth['token']}
        self.assertEqual(self.request('/api/profile','PUT',PROFILE,headers)[0],200)
        self.assertEqual(self.request('/api/applications','POST',{'offerId':'lab'},headers)[1]['application']['status'],'sent')
        status,bootstrap=self.request('/api/bootstrap',headers=headers)
        self.assertEqual(status,200);self.assertEqual(len(bootstrap['applications']),1)
        self.assertEqual(self.request('/api/bootstrap')[0],401)
        self.assertEqual(self.request('/api/auth','POST',{'devUserId':'x'},{'Origin':'https://evil.invalid'})[0],403)
        self.assertEqual(self.request('/api/catalog',headers={'Origin':'http://localhost:5173'})[0],200)
        self.assertEqual(self.request('/api/profile','PUT',[],headers)[0],400)

if __name__=='__main__': unittest.main()
