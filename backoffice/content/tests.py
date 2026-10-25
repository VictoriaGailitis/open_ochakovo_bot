import copy
import io
import json
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.test import TestCase, Client
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image
from backoffice.core.models import Material, MaterialVersion, MaterialQuestion, MaterialMedia
from .models import *
from .seed import seed_content
from .services import publish_level, check_level, save_material, material_value, presentation
from .forms import AssetForm, MediaForm, ModuleForm, MaterialForm
from server import catalog_store
from server.solutions import validate
from server.level_rules import runtime_rule_source

class ContentTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        seed_content()
        cls.actor = get_user_model().objects.create_superuser('content-admin', 'admin@example.invalid', 'test-pass-not-production')

    def test_seed_idempotent_and_all_levels_solvable(self):
        seed_content()
        self.assertEqual(LevelDefinition.objects.count(), 15)
        self.assertEqual(GameFamily.objects.count(), 6)
        for level in LevelDefinition.objects.all():
            self.assertTrue(check_level(level)[2]['solvable'])

    def test_public_catalog_has_no_private_snapshots_or_fixtures(self):
        public = catalog_store.catalog()
        self.assertEqual(len(public['tasks']), 15)
        for task in public['tasks']:
            self.assertNotIn('fixtures', task)
            self.assertNotIn('private_rule', task)
            self.assertNotIn('answers', task['puzzle'])
            self.assertGreater(task['contentVersion'], 0)
        self.assertNotIn('history-company-v1', json.dumps(public))

    def test_new_history_id_configured_without_source_change(self):
        source = LevelDefinition.objects.get(pk='history-1')
        new = LevelDefinition.objects.create(id='new-history', title='Новая история', family_id='history', level=2, description=source.description, direction=source.direction, points=9, puzzle=source.puzzle, presentation=source.presentation, fixtures=source.fixtures, rule_set=source.rule_set)
        self.assertIsNone(catalog_store.task(None, new.pk))
        publish_level(new, self.actor)
        task = catalog_store.task(None, new.pk)
        token = runtime_rule_source.set(catalog_store.resolve_rule)
        try:
            self.assertEqual(validate(task, source.fixtures['positive'][0]), [])
        finally:
            runtime_rule_source.reset(token)

    def test_edit_is_draft_until_publish_and_snapshots_immutable(self):
        level = LevelDefinition.objects.get(pk='signal-1')
        old = catalog_store.task(None, level.pk)
        level.title = 'Изменённый заголовок'
        level.save()
        self.assertEqual(catalog_store.task(None, level.pk)['title'], old['title'])
        publish_level(level)
        self.assertEqual(catalog_store.task(None, level.pk)['title'], level.title)
        version = level.versions.first()
        version.public_snapshot = {}
        with self.assertRaises(ValidationError):
            version.save()

    def test_invalid_positive_negative_or_private_rule_fails_closed(self):
        level = LevelDefinition.objects.get(pk='history-1')
        count = level.versions.count()
        for fixtures, rule in (({'positive': [{}], 'negative': [{}]}, level.rule_set), ({'positive': level.fixtures['positive'], 'negative': level.fixtures['positive']}, level.rule_set), (level.fixtures, None)):
            level.fixtures = fixtures
            level.rule_set = rule
            level.save()
            with self.assertRaises(ValidationError):
                publish_level(level)
        self.assertEqual(level.versions.count(), count)

    def test_archived_all_does_not_restore_file_levels(self):
        LevelDefinition.objects.update(status='archived')
        self.assertEqual(catalog_store.catalog()['tasks'], [])

    def test_scene_module_slots_and_role_bindings(self):
        level = LevelDefinition.objects.get(pk='signal-1')
        level.presentation = {'schemaVersion': 1, 'sprites': {}}
        level.save()
        module = SpriteModule.objects.get(pk='automation-scanner-module')
        LevelObject.objects.create(level=level, key='scan-decor', module=module, x=12, y=18, width=96, height=96)
        LevelObject.objects.create(level=level, key='live', sprite_id='automation-tray', binding='scanner')
        compiled = presentation(level)
        self.assertEqual(compiled['sprites']['scanner'], 'automation-tray')
        self.assertEqual(compiled['scene']['objects'][0]['x'], 12)
        obj = level.scene_objects.get(key='scan-decor')
        obj.x = 999
        obj.save()
        with self.assertRaises(ValidationError):
            presentation(level)

    def test_uploaded_asset_validation_and_published_identity_protection(self):
        stream = io.BytesIO()
        Image.new('RGBA', (16, 16)).save(stream, 'PNG')
        form = AssetForm(data={'id': 'new-png', 'title': 'New PNG', 'kind': 'general', 'width': 96, 'height': 96, 'active': True}, files={'upload': SimpleUploadedFile('sprite.png', stream.getvalue(), 'image/png')})
        self.assertTrue(form.is_valid(), form.errors)
        asset = form.save()
        self.assertEqual(catalog_store.asset(asset.pk)['mimeType'], 'image/png')
        invalid = AssetForm(data={'id': 'script', 'title': 'script', 'kind': 'general', 'width': 96, 'height': 96, 'active': True}, files={'upload': SimpleUploadedFile('image.svg', b'<svg onload="evil()"/>', 'image/svg+xml')})
        self.assertFalse(invalid.is_valid())
        current = SpriteAsset.objects.get(pk='automation-scanner')
        form = AssetForm(data={'id': current.pk, 'title': current.title, 'kind': current.kind, 'width': 97, 'height': 96, 'active': True}, instance=current)
        self.assertFalse(form.is_valid())

    def test_material_version_and_private_questions(self):
        material = Material.objects.get(pk='practice-first-steps')
        old = material.version
        value = json.loads(material.materialversion_set.get(version=old).snapshot)
        value['title'] = 'Новое название'
        save_material(material, value, self.actor, expected=old)
        self.assertEqual(material.version, old + 1)
        self.assertEqual(material.materialversion_set.count(), 2)
        self.assertEqual(MaterialQuestion.objects.filter(material=material, version=old).count(), 3)
        with self.assertRaises(ValidationError):
            save_material(material, value, expected=old)

    def test_media_upload_requires_content_and_audience_compatible(self):
        form = MediaForm(data={'id': 'video-test', 'audience': 'staff'}, files={'upload': SimpleUploadedFile('movie.mp4', b'xxxxftyp0000video', 'video/mp4')})
        self.assertTrue(form.is_valid(), form.errors)
        media = form.save()
        body = {'id': 'new-material', 'title': 'T', 'description': '', 'audience': 'candidate', 'category': 'video', 'published': True, 'demo': True, 'blocks': [{'type': 'video', 'mediaId': media.pk, 'title': 'Видео'}], 'quiz': None}
        with self.assertRaises(ValidationError):
            material_value(body)
        body['audience'] = 'staff'
        self.assertTrue(material_value(body))
        invalid = MediaForm(data={'id': 'wrong', 'audience': 'all'}, files={'upload': SimpleUploadedFile('movie.mp4', b'not a video', 'video/mp4')})
        self.assertFalse(invalid.is_valid())

    def test_admin_preview_permission_csrf_no_private_data_or_awards(self):
        level = LevelDefinition.objects.get(pk='history-1')
        url = reverse('admin:content_level_preview_data', args=[level.pk])
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.get(url).status_code, 302)
        user = get_user_model().objects.create_user('reader', is_staff=True)
        client.force_login(user)
        self.assertEqual(client.get(url).status_code, 403)
        user.user_permissions.add(Permission.objects.get(codename='view_leveldefinition'))
        self.assertEqual(client.get(url).status_code, 200)
        self.assertNotIn('answers', client.get(url).json()['task']['puzzle'])
        target = reverse('admin:content_level_preview_check', args=[level.pk])
        self.assertEqual(client.post(target, data=json.dumps({'solution': level.fixtures['positive'][0]}), content_type='application/json').status_code, 403)
        client.force_login(self.actor)
        client.get(reverse('admin:content_level_preview', args=[level.pk]))
        csrf = client.cookies['csrftoken'].value
        response = client.post(target, data=json.dumps({'solution': level.fixtures['positive'][0]}), content_type='application/json', HTTP_X_CSRFTOKEN=csrf)
        self.assertTrue(response.json()['correct'])
        self.assertEqual(response.json()['pointsAwarded'], 0)

    def test_admin_material_editor_get(self):
        self.client.force_login(self.actor)
        for name, pk in [('core_material_change', 'practice-first-steps'), ('content_leveldefinition_change', 'signal-1'), ('content_spriteasset_change', 'automation-scanner')]:
            response = self.client.get(reverse('admin:' + name, args=[pk]))
            self.assertEqual(response.status_code, 200)
            if name != 'content_spriteasset_change':
                self.assertContains(response, 'content-constructor')

    def test_reward_stock_cannot_drop_below_historical_exchanges(self):
        from backoffice.core.models import MiniUser, RewardExchange
        from .services import save_reward
        from .forms import RewardForm
        reward = PointReward.objects.first()
        MiniUser.objects.create(id='content-test-user')
        RewardExchange.objects.create(user_id='content-test-user', reward=reward.pk)
        data = {key: getattr(reward, key) for key in ('id', 'title', 'description', 'cost', 'stock', 'demo', 'published', 'archived')}
        data['stock'] = 0
        self.assertFalse(RewardForm(data=data, instance=reward).is_valid())
        reward.stock = 0
        with self.assertRaises(ValidationError):
            save_reward(reward, self.actor)
        reward.refresh_from_db()
        self.assertGreater(reward.stock, 0)
        reward.stock = 1
        save_reward(reward, self.actor)
        self.assertEqual(PointReward.objects.get(pk=reward.pk).stock, 1)

    def test_material_admin_post_creates_versioned_quiz(self):
        self.client.force_login(self.actor)
        quiz = {'points': 7, 'questions': [{'id': 'question', 'text': 'Вопрос', 'options': [{'id': 'yes', 'text': 'Да'}, {'id': 'no', 'text': 'Нет'}], 'correctOptionId': 'yes', 'explanation': 'Объяснение'}]}
        data = {'id': 'editor-material', 'title': 'Материал редактора', 'description': 'Описание', 'category': 'company', 'audience': 'candidate', 'published': '1', 'demo': '1', 'blocks_editor': json.dumps([{'type': 'heading', 'text': 'Заголовок'}, {'type': 'text', 'text': 'Текст'}]), 'quiz': json.dumps(quiz), '_save': 'Сохранить'}
        response = self.client.post(reverse('admin:core_material_add'), data)
        self.assertEqual(response.status_code, 302)
        material = Material.objects.get(pk='editor-material')
        self.assertEqual(material.points, 7)
        self.assertEqual(material.materialquestion_set.count(), 1)
        self.assertEqual(material.materialversion_set.count(), 1)
        data.update(expected_version='1', title='Новая версия')
        response = self.client.post(reverse('admin:core_material_change', args=[material.pk]), data)
        self.assertEqual(response.status_code, 302)
        material.refresh_from_db()
        self.assertEqual(material.version, 2)
        response = self.client.post(reverse('admin:core_material_change', args=[material.pk]), data)
        self.assertEqual(response.status_code, 200)
        material.refresh_from_db()
        self.assertEqual(material.version, 2)

    def test_published_asset_cannot_be_disabled_and_editor_draft_can_remove_object(self):
        asset = SpriteAsset.objects.get(pk='automation-scanner')
        form = AssetForm(data={'id': asset.pk, 'title': asset.title, 'kind': asset.kind, 'width': asset.width, 'height': asset.height, 'active': False}, instance=asset)
        self.assertFalse(form.is_valid())
        self.client.force_login(self.actor)
        level = LevelDefinition.objects.get(pk='signal-1')
        before = catalog_store.task(None, level.pk)
        LevelObject.objects.create(level=level, key='temporary', sprite_id=asset.pk, x=12, y=12, width=20, height=20)
        level.scene_objects.all().delete()
        self.assertEqual(catalog_store.task(None, level.pk), before)

    def test_material_preview_checks_quiz_without_reward_and_protects_access(self):
        material = Material.objects.get(pk='ochakovo-history')
        url = reverse('admin:content_material_preview', args=[material.pk])
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.actor)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Баллы в предпросмотре не начисляются')
        value = json.loads(material.materialversion_set.get(version=material.version).snapshot)
        answers = {'answer:' + q['id']: q['correctOptionId'] for q in value['quiz']['questions']}
        response = self.client.post(url, answers)
        self.assertContains(response, 'Все ответы верны')

    def test_malformed_constructor_data_has_validation_error(self):
        from .services import validate_presentation
        for value in ({'schemaVersion':1,'sprites':{'source':[]}}, {'schemaVersion':1,'sprites':{},'scene':{'width':358,'height':441,'objects':[{'id':'x','spriteId':[]}]}}):
            with self.assertRaises(ValidationError):validate_presentation(value)
        form=ModuleForm(data={'id':'zero-module','title':'Zero','kind':'general','width':0,'height':96,'slots':'[]','active':True});self.assertFalse(form.is_valid())

    def test_version_comparison_permissions_and_readonly_snapshots(self):
        source=LevelDefinition.objects.get(pk='history-1');source.title='Следующая публикация';source.save();publish_level(source)
        material=Material.objects.get(pk='practice-first-steps');value=json.loads(material.materialversion_set.get(version=material.version).snapshot);value['title']='Новая версия материала';save_material(material,value)
        urls=[reverse('admin:content_level_compare',args=[source.pk]),reverse('admin:content_material_compare',args=[material.pk])]
        for url in urls:self.assertEqual(self.client.get(url).status_code,302)
        reader=get_user_model().objects.create_user('version-reader',is_staff=True);self.client.force_login(reader)
        reader.user_permissions.add(Permission.objects.get(codename='view_leveldefinition'),Permission.objects.get(codename='view_material'))
        for url in urls:self.assertEqual(self.client.get(url).status_code,403)
        reader.user_permissions.add(Permission.objects.get(codename='view_levelversion'),Permission.objects.get(codename='view_materialversion'))
        response=self.client.get(urls[0]+'?a=1&b=2');self.assertEqual(response.status_code,200);self.assertContains(response,'Следующая публикация');self.assertNotContains(response,'history-company-v1');self.assertContains(response,'Приватные правила и проверочные решения скрыты')
        self.assertContains(self.client.get(urls[1]+'?a=1&b=2'),'Новая версия материала')
        self.assertEqual(self.client.get(urls[1]+'?a=999&b=2').status_code,404)
        self.client.force_login(self.actor);self.assertContains(self.client.get(urls[0]),'Приватные поля доступны');self.assertEqual(source.versions.count(),2);self.assertEqual(material.materialversion_set.count(),2)

    def test_shift_constructor_matches_frontend_node_geometry_and_format(self):
        from .validation import validate_task
        level=LevelDefinition.objects.get(pk='shift-1');task=check_level(level)[0];rule=level.rule_set.definition
        for mutate in (lambda p:p['scheme']['nodes'][0].update(display='rate'),lambda p:p['scheme']['nodes'][0].update(position={'x':351,'y':0}),lambda p:p['scheme']['nodes'][0].update(position={'x':0,'y':0,'width':100}),lambda p:p['metrics'][0].update(format={'decimals':2}),lambda p:p['scheme']['flows'][0].update(primary='yes')):
            invalid=copy.deepcopy(task);mutate(invalid['puzzle'])
            with self.assertRaises(ValidationError):validate_task(invalid,rule)
        valid=copy.deepcopy(task);valid['puzzle']['scheme']['nodes'][0].update(display='card',position={'x':12,'y':24});
        for flow in valid['puzzle']['scheme']['flows']:flow['primary']=False
        valid['puzzle']['scheme']['flows'][0]['primary']=True
        self.assertIsNotNone(validate_task(valid,rule))

    def test_content_list_headers_are_localized_without_changing_model_schema(self):
        from django.contrib import admin
        from django.test import RequestFactory
        request=RequestFactory().get('/admin/core/material/');request.user=self.actor
        display=admin.site._registry[Material].get_list_display(request);headers=[getattr(item,'short_description',item) for item in display]
        for title in ('Постоянный ID','Название','Категория','Аудитория','Опубликовано','Версия','Баллы'):self.assertIn(title,headers)
        title=next(item for item in display if getattr(item,'short_description','')=='Название');self.assertEqual(title.admin_order_field,'title');self.assertTrue(title(Material.objects.first()))
