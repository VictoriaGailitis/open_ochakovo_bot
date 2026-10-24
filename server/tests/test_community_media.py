"""Cross-portal visibility and authenticated uploaded media contracts."""
import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from server.app import API, Store, APIError, create_server, ACTIVITY_QR_PREFIX
from server.staff_auth import provision_account

PROFILE={'fullName':'Test Candidate','contact':'test@example.org','birthDate':'2000-01-01','direction':'undecided','availability':'Any','education':'College','consent':True}
PNG=b'\x89PNG\r\n\x1a\n'+b'test-fixture'


class CommunityMediaTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.store=Store(Path(self.temp.name)/'test.db')
        self.api=API(self.store,{'DEV_AUTH':'1','ADMIN_TOKEN':'test-admin'})
        self.admin={'X-Admin-Token':'test-admin'}
        auth=self.api.dispatch('POST','/api/auth',{'devUserId':'candidate'})
        self.candidate={'Authorization':'Bearer '+auth['token']}
        self.api.dispatch('PUT','/api/profile',PROFILE,self.candidate)
        with self.store.transaction() as db:
            provision_account(db,user_id='staff:employee',login='employee',password='Only-test-password!',role='employee')
        auth=self.api.dispatch('POST','/api/staff/login',{'login':'employee','password':'Only-test-password!'})
        self.staff={'Authorization':'Bearer '+auth['token']}
    def tearDown(self): self.temp.cleanup()
    def call(self,method,path,body=None,headers=None): return self.api.dispatch(method,path,body,headers or self.candidate)
    def failure(self,status,call):
        with self.assertRaises(APIError) as error: call()
        self.assertEqual(error.exception.status,status)
    def upload(self,audience='staff'):
        return self.call('POST','/api/admin/media',PNG,{**self.admin,'Content-Type':'image/png','X-Media-Audience':audience,'X-File-Name':'team.png'})['media']
    def material(self,asset,audience='staff',published=True):
        return self.call('POST','/api/admin/materials',{'title':'Team story','category':'stories','audience':audience,'published':published,'blocks':[{'type':'image','mediaId':asset['id'],'alt':'Team'}]},self.admin)['material']
    def test_internal_event_never_leaks_via_public_catalog_bootstrap_direct_registration_or_qr(self):
        public=self.call('GET','/api/catalog')
        self.assertNotIn('staff-community-day',json.dumps(public))
        self.assertNotIn('staff-community-day',json.dumps(self.call('GET','/api/bootstrap')))
        boot=self.call('GET','/api/community/bootstrap',headers=self.staff)
        self.assertIn('staff-community-day',[e['id'] for e in boot['events']])
        self.assertTrue(all(e['audience'] in ('staff','all') for e in boot['events']))
        self.failure(404,lambda:self.call('POST','/api/events/staff-community-day/registration'))
        with self.store.transaction() as db:
            activity=db.execute("SELECT * FROM event_activities WHERE id='staff-community-welcome'").fetchone()
            code=ACTIVITY_QR_PREFIX+activity['qr_token']
        self.failure(404,lambda:self.call('POST','/api/event-activities/scan',{'code':code}))
        first=self.call('POST','/api/event-activities/scan',{'code':code},self.staff)
        self.assertEqual(first['pointsAwarded'],20)
        self.assertEqual(self.call('POST','/api/event-activities/scan',{'code':code},self.staff)['pointsAwarded'],0)
        self.assertEqual(self.call('GET','/api/community/bootstrap',headers=self.staff)['balance'],20)
        self.assertNotIn(code,json.dumps(boot))
        with self.store.transaction() as db:
            db.execute("UPDATE event_activities SET active=0 WHERE id='staff-community-welcome'")
        self.failure(404,lambda:self.call('POST','/api/event-activities/scan',{'code':code}))
        self.failure(409,lambda:self.call('POST','/api/event-activities/scan',{'code':code},self.staff))
    def test_media_requires_published_material_and_matches_all_audience_boundaries(self):
        asset=self.upload()
        self.failure(404,lambda:self.call('GET','/api/media/'+asset['id'],headers=self.staff))
        material=self.material(asset,published=False)
        self.failure(404,lambda:self.call('GET','/api/media/'+asset['id'],headers=self.staff))
        self.call('PATCH','/api/admin/materials/'+material['id'],{'published':True},self.admin)
        self.assertEqual(self.call('GET','/api/media/'+asset['id'],headers=self.staff)['content'],PNG)
        self.failure(404,lambda:self.call('GET','/api/media/'+asset['id']))
        self.failure(401,lambda:self.api.dispatch('GET','/api/media/'+asset['id'],headers={}))
        self.failure(422,lambda:self.material(asset,'all'))
        self.call('POST','/api/admin/materials/'+material['id']+'/archive',{},self.admin)
        self.failure(404,lambda:self.call('GET','/api/media/'+asset['id'],headers=self.staff))
        self.assertEqual(self.call('GET','/api/admin/media/'+asset['id'],headers=self.admin)['content'],PNG)
    def test_upload_and_management_are_admin_only_and_files_are_not_active_html(self):
        self.failure(401,lambda:self.call('POST','/api/admin/media',PNG,{'Content-Type':'image/png'}))
        self.failure(415,lambda:self.call('POST','/api/admin/media',b'<script>alert(1)</script>',{**self.admin,'Content-Type':'image/png'}))
        self.failure(415,lambda:self.call('POST','/api/admin/media',b'<svg/>',{**self.admin,'Content-Type':'image/svg+xml'}))
        self.failure(422,lambda:self.upload('everybody'))
        asset=self.upload('all')
        self.material(asset,'all')
        self.assertEqual(self.call('GET','/api/media/'+asset['id'])['content'],PNG)
        self.assertEqual(self.call('GET','/api/media/'+asset['id'],headers=self.staff)['content'],PNG)
        self.assertNotIn('content',self.call('GET','/api/admin/media',headers=self.admin)['media'][0])
    def test_event_authoring_persists_audience_and_archive_closes_scan(self):
        definition={'title':'Internal workshop','description':'Description','date':'2030-11-20','startTime':'14:00','location':'Training room','type':'Workshop','capacity':2,'audience':'staff','published':True}
        event=self.call('POST','/api/admin/events',definition,self.admin)['event']
        self.assertNotIn(event['id'],json.dumps(self.call('GET','/api/catalog')))
        self.assertIn(event['id'],[e['id'] for e in self.call('GET','/api/community/bootstrap',headers=self.staff)['events']])
        self.call('POST','/api/events/'+event['id']+'/registration',{},self.staff)
        self.failure(409,lambda:self.call('PATCH','/api/admin/events/'+event['id'],{'audience':'all'},self.admin))
        self.call('DELETE','/api/admin/events/staff-community-day',{},self.admin)
        with self.store.transaction() as db: code=ACTIVITY_QR_PREFIX+db.execute("SELECT qr_token FROM event_activities WHERE id='staff-community-welcome'").fetchone()[0]
        self.failure(404,lambda:self.call('POST','/api/event-activities/scan',{'code':code},self.staff))
        API(Store(self.store.path),self.api.config)
        self.assertNotIn('staff-community-day',[e['id'] for e in self.call('GET','/api/community/bootstrap',headers=self.staff)['events']])
    def test_disabled_staff_cannot_read_internal_content_with_existing_token(self):
        asset=self.upload();self.material(asset)
        with self.store.transaction() as db: db.execute('UPDATE staff_credentials SET active=0')
        for path in ('/api/media/'+asset['id'],'/api/materials','/api/community/bootstrap'):
            self.failure(401,lambda:self.call('GET',path,headers=self.staff))


class MediaHTTPTest(unittest.TestCase):
    def test_binary_upload_and_authenticated_download_use_no_store_headers(self):
        with tempfile.TemporaryDirectory() as directory:
            server=create_server('127.0.0.1',0,Path(directory)/'test.db',{'DEV_AUTH':'1','ADMIN_TOKEN':'http-admin'})
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            base='http://127.0.0.1:'+str(server.server_port)
            def request(path,method='GET',body=None,headers=None):
                req=Request(base+path,method=method,data=body,headers=headers or {})
                try:
                    with urlopen(req,timeout=5) as response:return response.status,dict(response.headers),response.read()
                except HTTPError as error:return error.code,dict(error.headers),error.read()
            try:
                admin={'X-Admin-Token':'http-admin','Content-Type':'image/png','X-Media-Audience':'all'}
                self.assertEqual(request('/api/admin/media','POST',PNG,{'Content-Type':'image/png'})[0],401)
                status,_,raw=request('/api/admin/media','POST',PNG,admin)
                self.assertEqual(status,200);asset=json.loads(raw)['media']
                material={'title':'Photo','category':'company','audience':'all','published':True,'blocks':[{'type':'image','mediaId':asset['id'],'alt':'Photo'}]}
                self.assertEqual(request('/api/admin/materials','POST',json.dumps(material).encode(),{**admin,'Content-Type':'application/json'})[0],200)
                _,_,raw=request('/api/auth','POST',b'{"devUserId":"http"}',{'Content-Type':'application/json'})
                token=json.loads(raw)['token']
                status,headers,data=request('/api/media/'+asset['id'],headers={'Authorization':'Bearer '+token})
                self.assertEqual(status,200);self.assertEqual(data,PNG)
                self.assertEqual(headers['Content-Type'],'image/png')
                self.assertEqual(headers['Cache-Control'],'private, no-store')
                self.assertEqual(headers['X-Content-Type-Options'],'nosniff')
            finally:server.shutdown();server.server_close();thread.join()
