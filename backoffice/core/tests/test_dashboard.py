import io
import json
from types import SimpleNamespace

from django.contrib import admin
from django.contrib.auth.models import AnonymousUser, Group, Permission, User
from django.core.management import call_command
from django.db import connection
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext
from unfold.admin import ModelAdmin

from backoffice.dashboard import dashboard_callback
from backoffice.core.models import Application, CareerEvent, EventActivity, MiniUser


class DashboardLabelTests(SimpleTestCase):
    def test_event_label_is_title_and_date_with_safe_legacy_fallback(self):
        self.assertEqual(str(CareerEvent(id='event-a', definition=json.dumps({'title': 'Экскурсия', 'date': '2026-11-01'}))), 'Экскурсия · 2026-11-01')
        for invalid in ['[]', 'null', 'broken', '{}']:
            self.assertEqual(str(CareerEvent(id='event-a', definition=invalid)), 'event-a')

    def test_unprivileged_and_anonymous_dashboard_perform_no_domain_queries(self):
        # SimpleTestCase forbids database access: a forbidden count would fail.
        for user in [AnonymousUser(), SimpleNamespace(is_active=True, is_staff=True, has_perm=lambda _: False)]:
            request = RequestFactory().get('/admin/'); request.user = user
            self.assertEqual(dashboard_callback(request, {})['dashboard_sections'], [])

    def test_native_auth_admins_are_unfold_and_do_not_grant_domain_roles_auth_access(self):
        user = SimpleNamespace(has_perm=lambda permission: permission.startswith('core.'))
        request = RequestFactory().get('/admin/'); request.user = user
        for model in [User, Group]:
            registered = admin.site._registry[model]
            self.assertIsInstance(registered, ModelAdmin)
            self.assertFalse(registered.has_view_permission(request))
            self.assertFalse(registered.has_change_permission(request))
            self.assertFalse(registered.has_add_permission(request))
            self.assertFalse(registered.has_delete_permission(request))


class DashboardRoleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('setup_backoffice_roles', stdout=io.StringIO())
        person = MiniUser.objects.create(id='dashboard:candidate', profile='{"fullName":"PRIVATE PERSON","contact":"private@example.test"}')
        Application.objects.create(id='dashboard:app', user=person, offer='offer', profile=person.profile, status='sent')
        event = CareerEvent.objects.create(id='dashboard:event', definition='{"title":"Экскурсия"}', audience='all', published=1)
        EventActivity.objects.create(id='dashboard:activity', event=event, title='Активность', description='', points=10)
        cls.accounts = {}
        for role in ['HR', 'organizer', 'content_editor', 'game_editor']:
            user = User.objects.create_user(username='dashboard-' + role, password='dashboard-test-password', is_staff=True)
            user.groups.add(Group.objects.get(name=role))
            cls.accounts[role] = user.pk

    def request_for(self, role):
        request = RequestFactory().get('/admin/')
        request.user = User.objects.get(pk=self.accounts[role])
        request.user.get_all_permissions()  # Keep permission loading outside query assertions.
        return request

    def test_organizer_counts_only_permitted_entities_and_never_queries_candidate_or_private_data(self):
        with CaptureQueriesContext(connection) as queries:
            result = dashboard_callback(self.request_for('organizer'), {})
        labels = {card['label']: card['value'] for section in result['dashboard_sections'] for card in section['cards']}
        self.assertEqual(labels['Мероприятия'], 1)
        self.assertEqual(labels['Активности'], 1)
        self.assertNotIn('Отклики', labels)
        sql = '\n'.join(query['sql'] for query in queries)
        for table in ['applications', 'users', 'practice_checkins', 'analytics', 'application_referrals']:
            self.assertNotIn('FROM "' + table + '"', sql)
        self.assertNotIn('PRIVATE PERSON', repr(result))

    def test_hr_sees_status_totals_without_editor_or_organizer_counts(self):
        result = dashboard_callback(self.request_for('HR'), {})
        self.assertEqual([section['title'] for section in result['dashboard_sections']], ['Кандидаты и найм'])
        self.assertEqual(result['dashboard_sections'][0]['cards'][0]['value'], 1)
        self.assertEqual(result['dashboard_sections'][0]['statuses'][0]['value'], 1)
        self.assertNotIn('PRIVATE PERSON', repr(result))

    def test_editor_dashboard_respects_separate_material_and_game_permissions(self):
        material_result = dashboard_callback(self.request_for('content_editor'), {})
        game_result = dashboard_callback(self.request_for('game_editor'), {})
        material_labels = {card['label'] for section in material_result['dashboard_sections'] for card in section['cards']}
        game_labels = {card['label'] for section in game_result['dashboard_sections'] for card in section['cards']}
        self.assertEqual(material_labels, {'Материалы'})
        self.assertEqual(game_labels, {'Уровни', 'Черновики уровней', 'Спрайты'})

    def test_legacy_status_remains_visible_in_totals(self):
        Application.objects.filter(pk='dashboard:app').update(status='legacy-status')
        result = dashboard_callback(self.request_for('HR'), {})
        statuses = result['dashboard_sections'][0]['statuses']
        self.assertEqual(sum(item['value'] for item in statuses), 1)
        self.assertEqual(statuses[-1], {'label': 'Другие статусы', 'value': 1})

    def test_dashboard_template_and_auth_endpoints_keep_role_boundaries(self):
        self.client.force_login(User.objects.get(pk=self.accounts['organizer']))
        response = self.client.get('/admin/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Рабочий стол')
        self.assertContains(response, 'Мероприятия и активности')
        self.assertNotContains(response, 'PRIVATE PERSON')
        self.assertNotContains(response, 'private@example.test')
        self.assertNotContains(response, 'Кандидаты и найм')
        self.assertEqual(self.client.get('/admin/auth/user/').status_code, 403)
        self.assertEqual(self.client.get('/admin/auth/group/').status_code, 403)
        user = User.objects.get(pk=self.accounts['organizer'])
        user.user_permissions.add(Permission.objects.get(content_type__app_label='auth', codename='view_group'))
        self.assertEqual(self.client.get('/admin/auth/group/').status_code, 200)
        self.assertEqual(self.client.get('/admin/auth/user/').status_code, 403)
