"""The actual Django/PostgreSQL transport, not the retired SQLite oracle."""
import json
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from django.core.management import call_command
from django.db import close_old_connections,connection
from django.test import TestCase,TransactionTestCase,Client,override_settings
from backoffice.core.models import MiniUser,MaterialCompletion,LedgerEntry,EventActivity,StaffCredential,CareerEvent,EventRegistration,RewardExchange
from backoffice.content.models import PointReward
from server.app import APIError,ACTIVITY_QR_PREFIX
from server.django_api import PostgreSQLAPI
from server.postgres import runtime_store,translate
from server.staff_auth import provision_account

PROFILE={'fullName':'Тестовый Кандидат','contact':'runtime@example.org','birthDate':'2000-01-02','direction':'undecided','availability':'Готов','education':'Учебный колледж','consent':True}


class RuntimeTest(TestCase):
    @classmethod
    def setUpTestData(cls):call_command('bootstrap_miniapp',verbosity=0)
    def setUp(self):
        self.api=PostgreSQLAPI();self.api.config['DEV_AUTH']='1'
        auth=self.api.dispatch('POST','/api/auth',{'devUserId':'runtime'})
        self.headers={'Authorization':'Bearer '+auth['token']}
    def call(self,method,path,body=None,headers=None):return self.api.dispatch(method,path,body,headers or self.headers)
    def test_database_health_and_sql_parameter_translation(self):
        self.assertEqual(connection.vendor,'postgresql')
        self.assertEqual(self.call('GET','/api/health')['database'],'postgresql')
        self.assertEqual(translate("SELECT '?' AS literal WHERE ? LIKE '%yes%'"),"SELECT '?' AS literal WHERE %s LIKE '%%yes%%'")
        self.assertIn('(\"user_id\",\"task\",\"draft\",\"completed\",\"draft_revision\")',translate('INSERT INTO progress VALUES(?,?,?,?,?)'))
    def test_profile_age_and_public_bootstrap(self):
        bad={**PROFILE,'birthDate':'2015-01-01'}
        with self.assertRaises(APIError) as error:self.call('PUT','/api/profile',bad)
        self.assertEqual(error.exception.code,'age_restricted')
        self.call('PUT','/api/profile',PROFILE)
        result=self.call('GET','/api/bootstrap')
        self.assertEqual(result['profile']['fullName'],PROFILE['fullName'])
        self.assertEqual(result['balance'],0)
        self.assertNotIn('qr_token',json.dumps(result))
        self.assertTrue(result['catalog']['tasks'])
        self.assertNotIn('staff-community-day',[e['id'] for e in result['catalog']['events']])
    def test_staff_no_candidate_profile_history_qr_points_and_restart(self):
        store=runtime_store()
        with store.transaction() as db:
            provision_account(db,user_id='staff:runtime',login='runtime-staff',password='Runtime-password-123!',role='employee')
        token=self.api.dispatch('POST','/api/staff/login',{'login':'runtime-staff','password':'Runtime-password-123!'})['token']
        headers={'Authorization':'Bearer '+token}
        materials=self.call('GET','/api/materials',headers=headers)['materials']
        self.assertIn('inside-team',[m['id'] for m in materials])
        answer={'founded':'1978','event':'olympics','brand':'secret'}
        result=self.call('POST','/api/materials/ochakovo-history/complete',{'answers':answer},headers)
        self.assertEqual(result['pointsAwarded'],30)
        self.assertEqual(self.call('POST','/api/materials/ochakovo-history/complete',{'answers':answer},headers)['pointsAwarded'],0)
        activity=EventActivity.objects.get(pk='staff-community-welcome')
        code=ACTIVITY_QR_PREFIX+activity.qr_token
        scan=self.call('POST','/api/event-activities/scan',{'code':code},headers)
        self.assertEqual(scan['balance'],50)
        self.assertFalse(scan['alreadyCompleted'])
        self.assertEqual(self.call('POST','/api/event-activities/scan',{'code':code},headers)['pointsAwarded'],0)
        self.assertEqual(self.call('GET','/api/community/bootstrap',headers=headers)['balance'],50)
        self.assertIsNone(MiniUser.objects.get(pk='staff:runtime').profile)
        self.assertEqual(LedgerEntry.objects.filter(user_id='staff:runtime').count(),2)
        self.assertEqual(MaterialCompletion.objects.filter(user_id='staff:runtime').count(),1)
        self.assertEqual(PostgreSQLAPI().dispatch('GET','/api/community/bootstrap',headers=headers)['balance'],50)
    def test_http_transport_is_bearer_only_and_admin_cookies_do_not_grant_api_access(self):
        client=Client(enforce_csrf_checks=True)
        response=client.get('/api/health')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['database'],'postgresql')
        self.assertEqual(client.get('/api/health',CONTENT_LENGTH='').status_code,200)
        self.assertEqual(client.get('/api/bootstrap').status_code,401)
        with patch.dict('os.environ',{'DEV_AUTH':'1'}):
            response=client.post('/api/auth',json.dumps({'devUserId':'http-runtime'}),content_type='application/json')
        self.assertEqual(response.status_code,200)
        token=response.json()['token']
        self.assertEqual(client.get('/api/bootstrap',HTTP_AUTHORIZATION='Bearer '+token).status_code,200)
        self.assertEqual(client.post('/api/profile',b'{}',content_type='text/html',HTTP_AUTHORIZATION='Bearer '+token).status_code,415)
        self.assertNotIn('X-Frame-Options',client.get('/api/health'))
        self.assertEqual(client.get('/api/health')['Cache-Control'],'no-store')

    def test_missing_catalog_assets_and_trusted_https_proxy(self):
        client = Client()
        self.assertEqual(client.get('/api/game-assets/not-found').status_code, 404)
        with self.assertRaises(APIError) as missing:
            self.api.item('tasks', 'not-found')
        self.assertEqual(missing.exception.status, 404)
        with override_settings(SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO', 'https')):
            with patch.dict('os.environ', {'DEV_AUTH': '1'}):
                response = client.post('/api/auth', json.dumps({'devUserId': 'proxy-runtime'}),
                    content_type='application/json', HTTP_HOST='localhost', HTTP_ORIGIN='https://localhost',
                    HTTP_X_FORWARDED_PROTO='https')
        self.assertEqual(response.status_code, 200)

    def test_republished_level_rejects_old_draft_and_completion_without_writes(self):
        from backoffice.content.models import LevelDefinition
        from backoffice.content.services import publish_level
        from backoffice.core.models import GameProgress
        self.call('PUT','/api/profile',PROFILE)
        version=self.api.item('tasks','signal-1')['contentVersion']
        self.call('PUT','/api/tasks/signal-1/draft',{'draft':{'rules':[]},'revision':1,'contentVersion':version})
        level=LevelDefinition.objects.get(pk='signal-1')
        level.title='Обновлённый уровень';level.save()
        publish_level(level)
        before=GameProgress.objects.get(user_id='demo:runtime',task='signal-1').draft
        for method,action in [('PUT','draft'),('POST','complete')]:
            with self.assertRaises(APIError) as rejected:
                self.call(method,'/api/tasks/signal-1/'+action,{'draft':{'new':True},'revision':2,'solution':{},'contentVersion':version})
            self.assertEqual(rejected.exception.code,'task_changed')
        self.assertEqual(GameProgress.objects.get(user_id='demo:runtime',task='signal-1').draft,before)
        self.assertEqual(LedgerEntry.objects.count(),0)

    def test_legacy_shared_admin_token_cannot_bypass_personal_rbac(self):
        with patch.dict('os.environ', {'ADMIN_TOKEN': 'retired-test-token'}):
            response = Client().get('/api/admin/applications', HTTP_X_ADMIN_TOKEN='retired-test-token')
        self.assertEqual(response.status_code, 410)
        self.assertEqual(response.json()['code'], 'admin_api_retired')


class ConcurrentRuntimeTest(TransactionTestCase):
    reset_sequences=True
    def setUp(self):
        call_command('bootstrap_miniapp',verbosity=0)
        api=PostgreSQLAPI();api.config['DEV_AUTH']='1'
        token=api.dispatch('POST','/api/auth',{'devUserId':'parallel'})['token']
        self.headers={'Authorization':'Bearer '+token}
        api.dispatch('PUT','/api/profile',PROFILE,self.headers)
    def test_parallel_history_completions_share_one_legacy_award(self):
        def complete(_):
            close_old_connections()
            try:
                return PostgreSQLAPI().dispatch('POST','/api/materials/ochakovo-history/complete',{'answers':{'founded':'1978','event':'olympics','brand':'secret'}},self.headers)
            finally:connection.close()
        with ThreadPoolExecutor(max_workers=6) as pool:results=list(pool.map(complete,range(12)))
        self.assertEqual(sum(r['pointsAwarded'] for r in results),30)
        self.assertEqual(LedgerEntry.objects.filter(reason='task:history-1').count(),1)
        self.assertEqual(MaterialCompletion.objects.count(),1)

    def candidates(self):
        result=[]
        for index in range(6):
            api=PostgreSQLAPI();api.config['DEV_AUTH']='1'
            auth=api.dispatch('POST','/api/auth',{'devUserId':'capacity-'+str(index)})
            headers={'Authorization':'Bearer '+auth['token']}
            api.dispatch('PUT','/api/profile',PROFILE,headers)
            LedgerEntry.objects.create(id='capacity-balance-'+str(index),user_id=auth['userId'],reason='qa:initial',delta=100)
            result.append(headers)
        return result

    def concurrent_call(self,headers,path):
        def request(auth):
            close_old_connections()
            try:
                try:return PostgreSQLAPI().dispatch('POST',path,{},auth)
                except APIError as error:return {'code':error.code}
            finally:connection.close()
        with ThreadPoolExecutor(max_workers=6) as pool:return list(pool.map(request,headers))

    def test_different_users_cannot_overbook_last_event_place(self):
        event=CareerEvent.objects.get(pk='event-1')
        definition=json.loads(event.definition);definition.update(date='2035-01-01',capacity=1)
        event.definition=json.dumps(definition);event.save()
        results=self.concurrent_call(self.candidates(),'/api/events/event-1/registration')
        self.assertEqual(sum('registration' in result for result in results),1)
        self.assertEqual(sum(result.get('code')=='event_full' for result in results),5)
        self.assertEqual(EventRegistration.objects.filter(event=event,status='registered').count(),1)

    def test_different_users_cannot_exchange_last_reward_twice(self):
        reward=PointReward.objects.first();reward.stock=1;reward.cost=1;reward.save()
        results=self.concurrent_call(self.candidates(),'/api/rewards/'+reward.pk+'/exchange')
        self.assertEqual(sum('exchange' in result for result in results),1)
        self.assertEqual(sum(result.get('code')=='reward_unavailable' for result in results),5)
        self.assertEqual(RewardExchange.objects.filter(reward=reward.pk).count(),1)
        self.assertEqual(LedgerEntry.objects.filter(reason='exchange:'+reward.pk).count(),1)
