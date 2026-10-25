import io
import csv
import json
from datetime import date, timedelta
from uuid import uuid4
from django.contrib import admin
from django.contrib.admin.utils import quote
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.db import close_old_connections, connection, transaction
from django.test import Client, TestCase, TransactionTestCase
from concurrent.futures import ThreadPoolExecutor
from django.urls import reverse
from PIL import Image
from backoffice.core import models as core
from . import forms, models, services


class OperationsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('setup_backoffice_roles',stdout=io.StringIO(),stderr=io.StringIO())
        cls.superuser=get_user_model().objects.create_superuser('operations-root','ops@example.test','test-password-unpublished')
        cls.profile={'fullName':'Тестовый Кандидат','contact':'private-candidate@example.test','birthDate':'2000-05-01','direction':'lab','availability':'Лето','education':'Колледж','schedule':'День','consent':True,'futureContact':False,'consentedAt':'2024-01-01T10:00:00+00:00'}
        cls.candidate=core.MiniUser.objects.create(id='vk:operations-candidate',profile=json.dumps(cls.profile))
        cls.event=core.CareerEvent.objects.create(id='operations-event',definition=json.dumps({'id':'operations-event','title':'Встреча','description':'Описание','date':'2030-01-10','startTime':'12:00','location':'Москва','type':'Встреча','capacity':2,'program':['Знакомство'],'requirements':[],'demo':False}),audience='all',published=1)
        cls.activity=core.EventActivity.objects.create(event=cls.event,title='Экскурсия',description='Сканирование на площадке',points=20)
    def role_user(self,role):
        user=get_user_model().objects.create_user('role-'+role,is_staff=True)
        user.groups.add(Group.objects.get(name=role))
        return user
    def login(self,user=None):self.client.force_login(user or self.superuser)
    def staff(self,role='intern',uid=None):
        user=core.MiniUser.objects.create(id=uid or 'staff:'+str(uuid4()),profile='{}')
        credential=core.StaffCredential(user=user,login='test-'+str(uuid4()),role=role,active=1)
        services.save_staff(actor=self.superuser,credential=credential,password='secure-test-password-1')
        return user
    def event_data(self,**extra):
        return {'title':'Новое мероприятие','description':'Описание','date':'2030-01-10','startTime':'12:00','location':'Москва','type':'Встреча','capacity':'2','program':'Знакомство\nЭкскурсия','requirements':'Паспорт','audience':'all','published':'1',**extra}
    def profile_data(self,**extra):
        return {**self.profile,'correction_reason':'Исправление по запросу кандидата',**extra}
    def practice(self):
        user=self.staff()
        obj=core.Practice(user=user,title='Практика',department='Лаборатория',start_date='2030-01-01',end_date='2030-02-01',status='active',coordinator='{}',onboarding='[]',documents='[]',arrival='')
        services.save_practice(actor=self.superuser,practice=obj,reason='Назначение по договору')
        return obj

    def test_roles_are_idempotent_and_never_grant_auth_or_private_checkins(self):
        before={group.name:set(group.permissions.values_list('codename',flat=True)) for group in Group.objects.all()}
        call_command('setup_backoffice_roles',stdout=io.StringIO(),stderr=io.StringIO())
        for group in Group.objects.all():
            self.assertEqual(before[group.name],set(group.permissions.values_list('codename',flat=True)))
            self.assertFalse(group.permissions.filter(content_type__app_label='auth').exists())
            self.assertFalse(group.permissions.filter(codename__startswith='delete_').exists())
            self.assertFalse(group.permissions.filter(codename='view_private_checkins').exists())
        organizer=self.role_user('organizer')
        self.assertFalse(organizer.has_perm('operations.view_candidate_pii'))
        self.assertTrue(organizer.has_perm('operations.view_activity_qr'))

    def test_pii_and_private_checkins_are_separate_permissions(self):
        organizer=self.role_user('organizer');self.login(organizer)
        response=self.client.get(reverse('admin:core_miniuser_changelist'))
        self.assertEqual(response.status_code,403)
        self.assertNotContains(self.client.get(reverse('admin:core_rewardexchange_changelist')),self.profile['contact'])
        coordinator=self.role_user('coordinator');self.login(coordinator)
        self.assertEqual(self.client.get(reverse('admin:core_practicecheckin_changelist')).status_code,403)
        self.login(self.role_user('HR'))
        self.assertContains(self.client.get(reverse('admin:core_miniuser_change',args=[self.candidate.pk])),self.profile['contact'])

    def test_profile_correction_preserves_consent_and_rejects_underage(self):
        form=forms.ProfileForm(data=self.profile_data(fullName='Исправленное Имя',consentedAt='2099-01-01'),instance=self.candidate)
        self.assertTrue(form.is_valid(),form.errors)
        value=json.loads(form.instance.profile)
        self.assertEqual(value['consentedAt'],self.profile['consentedAt'])
        self.assertFalse(value['futureContact'])
        self.assertEqual(value['fullName'],'Исправленное Имя')
        today=date.today();birthday=today.replace(year=today.year-17)
        self.candidate.refresh_from_db()
        invalid=forms.ProfileForm(data=self.profile_data(birthDate=birthday.isoformat()),instance=self.candidate)
        self.assertFalse(invalid.is_valid())

    def test_admin_profile_correction_writes_audit_and_snapshot_is_immutable(self):
        application=core.Application.objects.create(user=self.candidate,offer='offer',profile=json.dumps(self.profile),status='sent')
        self.login()
        response=self.client.post(reverse('admin:core_miniuser_change',args=[self.candidate.pk]),self.profile_data(fullName='Новое Имя'))
        self.assertEqual(response.status_code,302)
        self.candidate.refresh_from_db();application.refresh_from_db()
        self.assertEqual(json.loads(self.candidate.profile)['fullName'],'Новое Имя')
        self.assertEqual(json.loads(application.profile),self.profile)
        self.assertEqual(models.ConsentHistory.objects.count(),1)
        audit=models.OperationsAudit.objects.get(action='candidate.corrected')
        self.assertNotIn(self.profile['contact'],json.dumps(audit.metadata))
        self.client.post(reverse('admin:core_application_change',args=[application.pk]),{'status':'reviewing','profile':'{"fullName":"Hacked"}'})
        application.refresh_from_db();self.assertEqual(json.loads(application.profile),self.profile)

    def test_privacy_request_is_csrf_protected_and_preserves_historical_consent(self):
        application=core.Application.objects.create(user=self.candidate,offer='privacy',profile=json.dumps(self.profile),status='sent')
        core.ApiSession.objects.create(token='hash-only-test',user=self.candidate,expires=9999999999)
        url=reverse('admin:operations_candidate_privacy',args=[self.candidate.pk])
        client=Client(enforce_csrf_checks=True);client.force_login(self.superuser)
        self.assertEqual(client.post(url,{'action':'anonymize','reason':'Запрос субъекта','confirm':'on'}).status_code,403)
        self.login();self.assertEqual(self.client.get(url).status_code,200)
        self.candidate.refresh_from_db();self.assertTrue(json.loads(self.candidate.profile)['consent'])
        services.privacy_action(actor=self.superuser,user=self.candidate,action='anonymize',reason='Запрос субъекта')
        self.candidate.refresh_from_db();application.refresh_from_db()
        self.assertFalse(json.loads(self.candidate.profile)['consent'])
        snapshot=json.loads(application.profile)
        self.assertEqual(snapshot['contact'],'')
        self.assertEqual(snapshot['consentedAt'],self.profile['consentedAt'])
        self.assertTrue(snapshot['consent'])
        self.assertFalse(core.ApiSession.objects.filter(user=self.candidate).exists())
        history=models.ConsentHistory.objects.get()
        history.reason='Изменить историю'
        with self.assertRaises(ValidationError):history.save()

    def test_staff_provision_hash_and_reset_revoke_sessions_without_django_account(self):
        before=get_user_model().objects.count()
        form=forms.StaffForm(data={'login':'new.employee','role':'employee','active':'1','staff_name':'Новый сотрудник','new_password':'secure-test-password-1'})
        self.assertTrue(form.is_valid(),form.errors)
        credential=form.save(commit=False)
        services.save_staff(actor=self.superuser,credential=credential,password=form.cleaned_data['new_password'],name=form.cleaned_data['staff_name'])
        from server.staff_auth import verify
        self.assertTrue(verify('secure-test-password-1',credential.password_hash))
        self.assertNotIn('secure-test-password',credential.password_hash)
        self.assertEqual(get_user_model().objects.count(),before)
        self.assertTrue(credential.user_id.startswith('staff:'))
        core.ApiSession.objects.create(token='staff-session-hash',user=credential.user,expires=9999999999)
        services.save_staff(actor=self.superuser,credential=credential,password='another-secure-password-2')
        self.assertFalse(core.ApiSession.objects.filter(user=credential.user).exists())
        self.login(self.role_user('technical_admin'))
        response=self.client.get(reverse('admin:core_staffcredential_change',args=[credential.pk]))
        self.assertNotContains(response,credential.password_hash)
        self.assertNotContains(response,'another-secure-password-2')
        for record in models.OperationsAudit.objects.all():
            self.assertNotIn(credential.password_hash,json.dumps(record.metadata))

    def test_staff_role_change_during_practice_is_rejected(self):
        practice=self.practice();credential=core.StaffCredential.objects.get(user=practice.user)
        credential.role='employee'
        with self.assertRaises(ValidationError):services.save_staff(actor=self.superuser,credential=credential)
        credential.refresh_from_db();self.assertEqual(credential.role,'intern')

    def test_qr_preview_download_permissions_and_stability(self):
        url=reverse('admin:operations_activity_qr',args=[self.activity.pk]);token=self.activity.qr_token
        self.assertEqual(self.client.get(url).status_code,302)
        self.login(self.role_user('HR'));self.assertEqual(self.client.get(url).status_code,403)
        organizer=self.role_user('organizer');self.login(organizer)
        response=self.client.get(url)
        self.assertEqual(response.status_code,200)
        self.assertNotContains(response,token)
        self.assertIn('no-store',response['Cache-Control'])
        response=self.client.get(url+'?format=png&download=1')
        self.assertEqual(response.status_code,200)
        self.assertEqual(Image.open(io.BytesIO(response.content)).format,'PNG')
        self.assertIn('attachment',response['Content-Disposition'])
        self.assertEqual(self.client.get(url+'?format=svg').get('Content-Type'),'image/svg+xml')
        self.activity.title='Новое имя';self.activity.save();self.activity.refresh_from_db()
        self.assertEqual(self.activity.qr_token,token)
        organizer.groups.clear();organizer.user_permissions.add(Permission.objects.get(codename='view_eventactivity',content_type__app_label='core'),Permission.objects.get(codename='manage_events',content_type__app_label='operations'))
        self.assertEqual(self.client.get(url+'?format=png').status_code,403)

    def test_event_structured_form_capacity_and_audience_guard(self):
        core.EventRegistration.objects.create(user=self.candidate,event=self.event,status='registered')
        second=core.MiniUser.objects.create(id='vk:second',profile=json.dumps(self.profile))
        core.EventRegistration.objects.create(user=second,event=self.event,status='registered')
        form=forms.EventForm(data=self.event_data(capacity='1'),instance=self.event)
        self.assertFalse(form.is_valid())
        self.event.refresh_from_db()
        form=forms.EventForm(data=self.event_data(audience='staff'),instance=self.event)
        self.assertFalse(form.is_valid())
        form=forms.EventForm(data=self.event_data(capacity='3'),instance=core.CareerEvent.objects.get(pk=self.event.pk))
        self.assertTrue(form.is_valid(),form.errors)
        event=form.save();definition=json.loads(event.definition)
        self.assertEqual(definition['program'],['Знакомство','Экскурсия'])
        self.assertEqual(definition['id'],event.pk)

    def test_registration_capacity_and_visibility(self):
        self.event.definition=json.dumps({**json.loads(self.event.definition),'capacity':1});self.event.save()
        core.EventRegistration.objects.create(user=self.candidate,event=self.event,status='registered')
        staff=self.staff('employee')
        form=forms.RegistrationForm(data={'user':staff.pk,'event':self.event.pk,'status':'registered'})
        self.assertFalse(form.is_valid())
        self.event.audience='staff';self.event.save()
        existing=core.EventRegistration.objects.get(user=self.candidate,event=self.event)
        form=forms.RegistrationForm(data={'user':self.candidate.pk,'event':self.event.pk,'status':'registered'},instance=existing)
        self.assertFalse(form.is_valid())

    def test_practice_assignment_history_and_invalid_period(self):
        practice=self.practice()
        self.assertEqual(models.MentorAssignmentHistory.objects.filter(practice=practice).count(),1)
        mentor_user=self.staff('mentor');mentor=core.Mentor.objects.create(user=mentor_user,name='Наставник',position='Инженер',contact='mentor@example.test')
        practice.mentor=mentor;services.save_practice(actor=self.superuser,practice=practice,reason='Назначен профильный наставник')
        self.assertEqual(models.MentorAssignmentHistory.objects.filter(practice=practice).count(),2)
        core.PracticeGoal.objects.create(practice=practice,title='Цель',description='Описание',criteria='Критерий',due_date='2030-01-15',status='planned',mentor_comment='',client_key='test')
        practice.end_date='2030-01-10'
        with self.assertRaises(ValidationError):services.save_practice(actor=self.superuser,practice=practice,reason='Сокращение')

    def test_goal_version_and_period(self):
        practice=self.practice()
        goal=core.PracticeGoal.objects.create(practice=practice,title='Цель',description='Описание',criteria='Критерий',due_date='2030-01-15',status='planned',mentor_comment='',client_key='test')
        data={'practice':practice.pk,'title':'Цель','description':'Описание','criteria':'Критерий','due_date':'2030-01-15','status':'in_progress','mentor_comment':'','expected_version':'0'}
        form=forms.GoalForm(data=data,instance=goal);self.assertFalse(form.is_valid())
        goal.refresh_from_db();data.update(expected_version='1',due_date='2031-01-01')
        self.assertFalse(forms.GoalForm(data=data,instance=goal).is_valid())
        goal.refresh_from_db();data['due_date']='2030-01-15'
        form=forms.GoalForm(data=data,instance=goal)
        self.assertTrue(form.is_valid(),form.errors)

    def test_compensation_is_idempotent_nonnegative_and_audited(self):
        actor=self.role_user('technical_admin');key=uuid4()
        one=services.adjust_points(actor=actor,user=self.candidate,delta=30,reason='Компенсация сбоя',idempotency_key=key)
        two=services.adjust_points(actor=actor,user=self.candidate,delta=30,reason='Компенсация сбоя',idempotency_key=key)
        self.assertEqual(one.pk,two.pk)
        self.assertEqual(core.LedgerEntry.objects.filter(user=self.candidate).count(),1)
        with self.assertRaises(ValidationError):services.adjust_points(actor=actor,user=self.candidate,delta=-31,reason='Ошибка',idempotency_key=uuid4())
        with self.assertRaises(ValidationError):services.adjust_points(actor=actor,user=self.candidate,delta=50,reason='Другая сумма',idempotency_key=key)
        with self.assertRaises(PermissionDenied):services.adjust_points(actor=self.role_user('organizer'),user=self.candidate,delta=10,reason='Нет права',idempotency_key=uuid4())
        self.assertEqual(models.OperationsAudit.objects.filter(action='points.compensated').count(),1)

    def test_immutable_awards_cannot_be_edited_in_admin(self):
        ledger=core.LedgerEntry.objects.create(user=self.candidate,reason='task:test',delta=20)
        self.login()
        response=self.client.post(reverse('admin:core_ledgerentry_change',args=[ledger.pk]),{'delta':'9999','reason':'hacked'})
        self.assertEqual(response.status_code,403)
        ledger.refresh_from_db();self.assertEqual(ledger.delta,20)
        self.assertEqual(self.client.post(reverse('admin:core_ledgerentry_delete',args=[ledger.pk]),{'post':'yes'}).status_code,403)

    def test_confirmed_hire_and_fulfilment_create_no_points(self):
        referrer=self.staff();code=core.ReferralCode.objects.create(code='OPS-TEST-CODE',user=referrer)
        application=core.Application.objects.create(user=self.candidate,offer='referral',profile=json.dumps(self.profile),status='accepted')
        core.ApplicationReferral.objects.create(application=application,code=code,referrer_user=referrer,referrer_name='Практикант')
        self.assertFalse(core.ReferralMerchReward.objects.exists())
        first=services.confirm_hire(actor=self.superuser,application=application)
        second=services.confirm_hire(actor=self.superuser,application=application)
        self.assertFalse(first['alreadyConfirmed']);self.assertTrue(second['alreadyConfirmed'])
        reward=core.ReferralMerchReward.objects.get()
        fulfilment=models.Fulfilment(referral_reward=reward,item='Мерч за рекомендацию',status='issued')
        services.save_fulfilment(actor=self.superuser,fulfilment=fulfilment)
        reward.refresh_from_db();self.assertEqual(reward.status,'issued')
        self.assertIsNotNone(fulfilment.issued_at)
        self.assertFalse(core.LedgerEntry.objects.exists())
        with self.assertRaises(ValidationError):services.save_fulfilment(actor=self.superuser,fulfilment=fulfilment)

    def test_all_operational_list_pages_and_structured_add_forms_render(self):
        self.login()
        managed=(core.MiniUser,core.Application,core.StaffCredential,core.CareerEvent,core.EventActivity,core.EventRegistration,core.Mentor,core.Practice,core.PracticeGoal,core.PracticeMeeting,core.PracticeRequest,models.LedgerAdjustment,models.Fulfilment)
        for model in managed:
            with self.subTest(model=model.__name__):
                admin_model=admin.site._registry[model]
                self.assertEqual(self.client.get(reverse('admin:'+model._meta.app_label+'_'+model._meta.model_name+'_changelist')).status_code,200)
                from django.test import RequestFactory
                request=RequestFactory().get('/admin/');request.user=self.superuser
                if admin_model.has_add_permission(request):
                    self.assertEqual(self.client.get(reverse('admin:'+model._meta.app_label+'_'+model._meta.model_name+'_add')).status_code,200)
        practice=self.practice()
        practice.status='completed';practice.save()
        self.assertEqual(self.client.get(reverse('admin:core_practice_change',args=[practice.pk])).status_code,200)
        self.candidate.profile=json.dumps({**self.profile,'consent':False});self.candidate.save()
        self.assertEqual(self.client.get(reverse('admin:core_miniuser_change',args=[self.candidate.pk])).status_code,200)

    def test_admin_practice_and_goal_submission_and_coordinator_reply(self):
        user=self.staff();self.login(self.role_user('coordinator'))
        response=self.client.post(reverse('admin:core_practice_add'),{'user':user.pk,'mentor':'','title':'Практика из админки','department':'Лаборатория','start_date':'2030-01-01','end_date':'2030-02-01','status':'scheduled','arrival':'','coordinator_name':'Координатор','coordinator_contact':'coordinate@example.test','onboarding_lines':['arrival'],'document_lines':'Паспорт | Принести оригинал','assignment_reason':'Назначение по договору'})
        self.assertEqual(response.status_code,302)
        practice=core.Practice.objects.get(user=user)
        self.assertEqual(practice.start_date,'2030-01-01')
        self.assertEqual(json.loads(practice.onboarding),['arrival'])
        self.assertEqual(json.loads(practice.documents)[0]['title'],'Паспорт')
        response=self.client.post(reverse('admin:core_practicegoal_add'),{'practice':practice.pk,'title':'Освоить процесс','description':'Наблюдение на площадке','criteria':'Показать наставнику','due_date':'2030-01-15','status':'planned','mentor_comment':'','expected_version':'1'})
        self.assertEqual(response.status_code,302)
        goal=core.PracticeGoal.objects.get(practice=practice)
        self.assertTrue(goal.client_key.startswith('admin:'))
        self.assertEqual(goal.due_date,'2030-01-15')
        request=core.PracticeRequest.objects.create(practice=practice,target='coordinator',topic='Документы',body='Как получить пропуск?',status='received',response='',client_key='test-inbox')
        response=self.client.post(reverse('admin:core_practicerequest_change',args=[request.pk]),{'status':'resolved','response':'Подойдите на стойку координатора.','expected_version':'1'})
        self.assertEqual(response.status_code,302)
        request.refresh_from_db();self.assertEqual(request.version,2);self.assertEqual(request.status,'resolved')

    def test_operational_forms_have_russian_labels_and_compact_widgets(self):
        form=forms.ActivityForm()
        self.assertEqual(form.fields['event'].label,'Мероприятие')
        self.assertEqual(form.fields['title'].label,'Название')
        from django import forms as django_forms
        self.assertIsInstance(form.fields['title'].widget,django_forms.TextInput)
        self.assertEqual(form.fields['description'].widget.attrs['rows'],4)
        self.assertEqual(forms.StaffForm().fields['login'].label,'Логин')
        self.assertIsInstance(forms.MentorForm().fields['name'].widget,django_forms.TextInput)
        self.login()
        response=self.client.get(reverse('admin:core_eventactivity_add'))
        self.assertContains(response,'Мероприятие')
        self.assertContains(response,'Описание')
        self.assertNotContains(response,'>Title:')
        response=self.client.get(reverse('admin:core_application_add'))
        self.assertEqual(response.status_code,403)
        response=self.client.get(reverse('admin:core_eventactivity_changelist'))
        self.assertContains(response,'Название')
        self.assertContains(response,'Мероприятие')
        self.assertContains(response,'Баллы')
        self.assertNotContains(response,'>Title<')
        self.assertContains(response,'Встреча')

    def test_localized_list_headers_preserve_change_links_and_column_sorting(self):
        self.login()
        core.EventActivity.objects.create(event=self.event,title='Меньше баллов',description='Описание',points=5)
        response=self.client.get(reverse('admin:core_eventactivity_changelist')+'?o=2')
        self.assertEqual(list(response.context_data['cl'].result_list.values_list('points',flat=True)),[5,20])
        self.assertContains(response,reverse('admin:core_eventactivity_change',args=[quote(self.activity.pk)]))
        user=self.staff('employee')
        response=self.client.get(reverse('admin:core_staffcredential_changelist'))
        staff_url=reverse('admin:core_staffcredential_change',args=[quote(user.pk)])
        self.assertContains(response,staff_url)
        self.assertEqual(self.client.get(staff_url).status_code,200)
        application=core.Application.objects.create(id='linked_app_42',user=self.candidate,offer='linked-offer',profile=json.dumps(self.profile),status='sent')
        response=self.client.get(reverse('admin:core_application_changelist'))
        application_url=reverse('admin:core_application_change',args=[quote(application.pk)])
        self.assertContains(response,application_url)
        self.assertEqual(self.client.get(application_url).status_code,200)

    def test_staff_name_edit_preserves_profile_and_is_audited_without_candidate_changes(self):
        user=self.staff('employee');credential=core.StaffCredential.objects.get(user=user)
        original={'fullName':'Старое Имя','preference':'keep','consent':False,'consentedAt':'historical-staff-value'}
        user.profile=json.dumps(original);user.save()
        self.assertEqual(forms.StaffForm(instance=credential).fields['staff_name'].initial,'Старое Имя')
        self.login(self.role_user('technical_admin'))
        response=self.client.post(reverse('admin:core_staffcredential_change',args=[user.pk]),{'login':credential.login,'role':'employee','active':'1','staff_name':'Новое Имя','new_password':''})
        self.assertEqual(response.status_code,302)
        user.refresh_from_db();self.candidate.refresh_from_db()
        self.assertEqual(json.loads(user.profile),{**original,'fullName':'Новое Имя'})
        self.assertEqual(json.loads(self.candidate.profile),self.profile)
        record=models.OperationsAudit.objects.filter(action='staff.updated').latest('pk')
        self.assertIn('staff_name',record.metadata['fields'])
        self.assertNotIn('Новое Имя',json.dumps(record.metadata))
        services.save_staff(actor=self.superuser,credential=credential,name='')
        user.refresh_from_db();self.assertEqual(json.loads(user.profile)['fullName'],'Новое Имя')

    def test_filtered_csv_export_needs_explicit_permission_and_sanitizes_cells(self):
        profile={**self.profile,'fullName':'=HYPERLINK("https://example.test")','contact':'+79991234567','education':'  @SUM(1,2)'}
        included=core.Application.objects.create(user=self.candidate,offer='csv-included',profile=json.dumps(profile),status='reviewing')
        excluded=core.Application.objects.create(user=self.candidate,offer='csv-excluded',profile=json.dumps(self.profile),status='sent')
        url=reverse('admin:core_application_export_csv')+'?status__exact=reviewing'
        hr=self.role_user('HR');self.login(hr)
        self.assertEqual(self.client.get(url).status_code,403)
        self.assertNotContains(self.client.get(reverse('admin:core_application_changelist')),'Скачать CSV')
        hr.user_permissions.add(Permission.objects.get(content_type__app_label='operations',codename='export_candidate_data'))
        response=self.client.get(url)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response['Content-Type'],'text/csv; charset=utf-8')
        self.assertIn('no-store',response['Cache-Control'])
        rows=list(csv.reader(io.StringIO(response.content.decode('utf-8-sig'))))
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[1][0],included.pk)
        self.assertTrue(rows[1][5].startswith("'="))
        self.assertTrue(rows[1][6].startswith("'+"))
        self.assertTrue(rows[1][9].startswith("'  @"))
        record=models.OperationsAudit.objects.get(action='applications.exported')
        self.assertEqual(record.metadata,{'application_ids':[included.pk],'count':1})
        self.assertNotIn(profile['contact'],json.dumps(record.metadata))
        response=self.client.get(reverse('admin:core_application_changelist')+'?status__exact=reviewing')
        self.assertIn(reverse('admin:core_application_export_csv')+'?status__exact=reviewing',[item['path'] for item in response.context_data['actions_list']])
        excluded.refresh_from_db();self.assertEqual(excluded.status,'sent')
        # The export capability by itself cannot grant access to candidate data.
        outsider=self.role_user('organizer')
        outsider.user_permissions.add(Permission.objects.get(content_type__app_label='operations',codename='export_candidate_data'),Permission.objects.get(content_type__app_label='core',codename='view_application'))
        self.login(outsider);self.assertEqual(self.client.get(url).status_code,403)


class ConcurrentOperationsTests(TransactionTestCase):
    reset_sequences=True
    def setUp(self):
        self.actor=get_user_model().objects.create_superuser('parallel-ops','parallel@example.test','unpublished-test-password')
        self.user=core.MiniUser.objects.create(id='vk:concurrent-ops')
    def test_concurrent_compensation_same_key_is_one_ledger_entry(self):
        key=uuid4()
        def apply(_):
            close_old_connections()
            try:return services.adjust_points(actor=self.actor,user=self.user,delta=20,reason='Один компенсируемый сбой',idempotency_key=key).pk
            finally:connection.close()
        with ThreadPoolExecutor(max_workers=4) as pool:ids=list(pool.map(apply,range(8)))
        self.assertEqual(len(set(ids)),1)
        self.assertEqual(core.LedgerEntry.objects.filter(user=self.user).count(),1)
        self.assertEqual(models.LedgerAdjustment.objects.count(),1)
    def test_registration_workers_cannot_overbook(self):
        profile={'fullName':'Параллельный Кандидат','contact':'parallel@example.test','birthDate':'2000-01-01','direction':'lab','availability':'Лето','education':'Колледж','consent':True}
        self.user.profile=json.dumps(profile);self.user.save()
        other=core.MiniUser.objects.create(id='vk:other-parallel',profile=json.dumps(profile))
        event=core.CareerEvent.objects.create(definition=json.dumps({'title':'Последнее место','date':'2030-01-01','capacity':1}),audience='all',published=1)
        def register(uid):
            close_old_connections()
            try:
                with transaction.atomic():
                    form=forms.RegistrationForm(data={'user':uid,'event':event.pk,'status':'registered'})
                    if not form.is_valid():return False
                    form.save();return True
            finally:connection.close()
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(register,[self.user.pk,other.pk]))
        self.assertEqual(sum(results),1)
        self.assertEqual(core.EventRegistration.objects.filter(event=event,status='registered').count(),1)
    def test_concurrent_hiring_different_applications_has_one_candidate_entitlement(self):
        referrer=core.MiniUser.objects.create(id='staff:parallel-referrer',profile='{}')
        code=core.ReferralCode.objects.create(code='PARALLEL-CODE',user=referrer)
        applications=[]
        for index in range(2):
            application=core.Application.objects.create(user=self.user,offer='parallel-offer-'+str(index),profile='{}',status='accepted')
            core.ApplicationReferral.objects.create(application=application,code=code,referrer_user=referrer,referrer_name='Практикант')
            applications.append(application)
        def hire(application):
            close_old_connections()
            try:
                try:services.confirm_hire(actor=self.actor,application=application);return 'confirmed'
                except ValidationError:return 'rejected'
            finally:connection.close()
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(hire,applications))
        self.assertEqual(results.count('confirmed'),1)
        self.assertEqual(core.ReferralMerchReward.objects.filter(hired_candidate_user=self.user).count(),1)
        self.assertEqual(models.OperationsAudit.objects.filter(action='referral.hire_confirmed').count(),1)
        self.assertFalse(core.LedgerEntry.objects.exists())
