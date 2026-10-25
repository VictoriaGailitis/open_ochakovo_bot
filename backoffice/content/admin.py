import json
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import JsonResponse, HttpResponse
from django.shortcuts import redirect, get_object_or_404
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST
from unfold.admin import ModelAdmin, TabularInline
from backoffice.core.models import Material, MaterialMedia, MaterialVersion, MaterialQuestion, MaterialCompletion
from .models import *
from .forms import *
from . import services

def snapshot_differences(before,after,path=''):
    if isinstance(before,dict) and isinstance(after,dict):
        rows=[]
        for key in sorted(set(before)|set(after)):
            rows.extend(snapshot_differences(before.get(key),after.get(key),path+'.'+key if path else key))
        return rows
    if isinstance(before,list) and isinstance(after,list):
        rows=[]
        for index in range(max(len(before),len(after))):
            rows.extend(snapshot_differences(before[index] if index<len(before) else None,after[index] if index<len(after) else None,f'{path}[{index}]'))
        return rows
    return [] if before==after else [{'path':path,'before':json.dumps(before,ensure_ascii=False,indent=2),'after':json.dumps(after,ensure_ascii=False,indent=2)}]


def compare_context(request,versions,decode):
    versions=list(versions)
    if not versions:return None
    try:
        first=int(request.GET.get('a',versions[-2].version if len(versions)>1 else versions[-1].version))
        second=int(request.GET.get('b',versions[-1].version))
    except (TypeError,ValueError):return None
    a=next((v for v in versions if v.version==first),None);b=next((v for v in versions if v.version==second),None)
    if a is None or b is None:return None
    return {'versions':versions,'first':first,'second':second,'differences':snapshot_differences(decode(a),decode(b))}


class AuditedAdmin(ModelAdmin):
    def get_list_display(self,request):
        result=[]
        for item in super().get_list_display(request):
            if not isinstance(item,str) or item not in FIELD_LABELS:
                result.append(item);continue
            def display(obj,name=item):
                value=getattr(obj,name)
                return bool(value) if name in ('published','archived','demo') else value
            display.short_description=FIELD_LABELS[item]
            display.admin_order_field=item
            display.__name__='localized_'+item
            if item in ('published','archived','demo'):display.boolean=True
            result.append(display)
        return tuple(result)


    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        try:
            return super().changeform_view(request, object_id, form_url, extra_context)
        except ValidationError as error:
            if request.method != 'POST':
                raise
            messages.error(request, '; '.join(error.messages))
            return redirect(request.path)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        services.audit(request.user, 'content.change' if change else 'content.create', obj, form.changed_data)

    def has_delete_permission(self, request, obj=None):
        return False

class SnapshotAdmin(AuditedAdmin):

    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in self.model._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

class LevelObjectInline(TabularInline):
    model = LevelObject
    form = ObjectForm
    extra = 0
    tab = True

    def has_delete_permission(self, request, obj=None):
        return request.user.has_perm('content.change_leveldefinition')
    fields = ('key', 'sprite', 'module', 'binding', 'slot_values', 'x', 'y', 'width', 'height', 'rotation', 'layer')

@admin.register(LevelDefinition)
class LevelAdmin(AuditedAdmin):
    form = LevelForm
    inlines = (LevelObjectInline,)
    list_display = ('id', 'title', 'family', 'level', 'status', 'published_version', 'points')
    list_filter = ('family', 'status')
    search_fields = ('id', 'title')
    readonly_fields = ('status', 'published_version', 'updated_at', 'preview_link','compare_link')
    fieldsets = (('Уровень', {'fields': ('id', 'title', 'family', 'level', 'description', 'direction', 'points', 'duration', 'offer_id', 'demo', 'explanation', 'career_explanation')}), ('Задача и оформление', {'fields': ('puzzle', 'presentation')}), ('Приватная проверка и публикация', {'fields': ('rule_set', 'fixtures', 'expected_updated', 'preview_link','compare_link', 'status', 'published_version', 'updated_at')}))

    def save_model(self, request, obj, form, change):
        if change:
            current = LevelDefinition.objects.select_for_update().get(pk=obj.pk)
            services.require(form.cleaned_data.get('expected_updated') == current.updated_at.isoformat(), 'Черновик уровня изменён в другой вкладке. Обновите страницу.')
        super().save_model(request, obj, form, change)

    def save_formset(self, request, form, formset, change):
        super().save_formset(request, form, formset, change)
        services.audit(request.user, 'level.scene_change', form.instance, ['scene_objects'])

    @admin.display(description='Сравнение версий')
    def compare_link(self,obj):return format_html('<a href="{}">Сравнить опубликованные версии</a>',reverse('admin:content_level_compare',args=[obj.pk])) if obj and not obj._state.adding and obj.published_version else 'После первой публикации'

    def preview_link(self, obj):
        return format_html('<a href="{}">Открыть предпросмотр и проверку публикации</a>', reverse('admin:content_level_preview', args=[obj.pk])) if obj and not obj._state.adding else 'Сначала сохраните черновик.'
    preview_link.short_description = 'Предпросмотр'

    def get_changeform_initial_data(self, request):
        return {'family': request.GET.get('family', 'signal'), 'presentation': {'schemaVersion': 1, 'sprites': {}}}

    def add_view(self, request, form_url='', extra_context=None):
        if request.method == 'GET' and (not request.GET.get('family')):
            return TemplateResponse(request, 'content/choose_family.html', {**self.admin_site.each_context(request), 'title': 'Выберите механику уровня', 'families': GameFamily.objects.all()})
        return super().add_view(request, form_url, extra_context)

    def get_urls(self):
        return [path('<path:object_id>/compare/',self.admin_site.admin_view(self.compare),name='content_level_compare'),path('<path:object_id>/preview/', self.admin_site.admin_view(self.preview), name='content_level_preview'), path('<path:object_id>/preview-data/', self.admin_site.admin_view(self.preview_data), name='content_level_preview_data'), path('<path:object_id>/preview-check/', self.admin_site.admin_view(csrf_protect(require_POST(self.preview_check))), name='content_level_preview_check'), path('<path:object_id>/publish/', self.admin_site.admin_view(csrf_protect(require_POST(self.publish))), name='content_level_publish'), path('<path:object_id>/archive/', self.admin_site.admin_view(csrf_protect(require_POST(self.archive))), name='content_level_archive')] + super().get_urls()

    def permitted(self, request, object_id, publish=False):
        obj = get_object_or_404(LevelDefinition, pk=object_id)
        if not self.has_view_or_change_permission(request, obj) or (publish and (not request.user.has_perm('content.publish_leveldefinition'))):
            raise PermissionDenied
        return obj

    def compare(self,request,object_id):
        obj=self.permitted(request,object_id)
        if not request.user.has_perm('content.view_levelversion'):raise PermissionDenied
        private=request.user.has_perm('content.view_ruleset')
        def snapshot(version):return {'public_snapshot':version.public_snapshot,**({'private_rule':version.private_rule,'fixtures':version.fixtures} if private else {})}
        context=compare_context(request,obj.versions.order_by('version'),snapshot)
        if context is None:return HttpResponse(status=404)
        return TemplateResponse(request,'content/compare.html',{**self.admin_site.each_context(request),**context,'title':'Сравнение версий уровня: '+obj.title,'back_url':reverse('admin:content_leveldefinition_change',args=[obj.pk]),'private_visible':private})

    def preview(self, request, object_id):
        obj = self.permitted(request, object_id)
        try:
            _, _, report = services.check_level(obj)
            errors = []
        except ValidationError as error:
            report = None
            errors = error.messages
        return TemplateResponse(request, 'content/level_preview.html', {**self.admin_site.each_context(request), 'title': 'Предпросмотр: ' + obj.title, 'level': obj, 'report': report, 'errors': errors, 'can_publish': request.user.has_perm('content.publish_leveldefinition')})

    def preview_data(self, request, object_id):
        obj = self.permitted(request, object_id)
        try:
            return JsonResponse({'task': services.task_snapshot(obj)})
        except (ValidationError, KeyError, TypeError) as error:
            return JsonResponse({'message': '; '.join(getattr(error, 'messages', ['Проверьте структуру черновика.']))}, status=422)

    def preview_check(self, request, object_id):
        obj = self.permitted(request, object_id)
        from server.solutions import validate
        from server.level_rules import LevelRuleRegistry
        try:
            body = json.loads(request.body)
            task = services.task_snapshot(obj)
            rule = obj.rule_set.definition if obj.rule_set_id else None
            registry = LevelRuleRegistry({'schemaVersion': 1, 'levels': {task['id']: 'preview'}, 'rules': {'preview': rule}}) if rule else None
            errors = validate(task, body.get('solution'), registry)
            result = {'correct': not errors, 'errors': errors, 'explanation': task['explanation'] if not errors else '', 'pointsAwarded': 0, 'alreadyCompleted': False, 'balance': 0, 'progress': {}}
            if not errors and task['game'] == 'shift':
                from server.shift import completion_details
                result.update(completion_details(task, registry))
            return JsonResponse(result)
        except (ValueError, KeyError, TypeError, ValidationError):
            return JsonResponse({'message': 'Некорректное решение или структура черновика.'}, status=422)

    def publish(self, request, object_id):
        obj = self.permitted(request, object_id, True)
        if not self.has_change_permission(request, obj):
            raise PermissionDenied
        try:
            obj, _ = services.publish_level(obj, request.user)
            messages.success(request, 'Проверки пройдены. Версия ' + str(obj.published_version) + ' опубликована.')
        except ValidationError as error:
            messages.error(request, '; '.join(error.messages))
        return redirect('admin:content_level_preview', object_id)

    def archive(self, request, object_id):
        obj = self.permitted(request, object_id, True)
        if not self.has_change_permission(request, obj):
            raise PermissionDenied
        obj.status = 'archived'
        obj.save(update_fields=['status', 'updated_at'])
        services.audit(request.user, 'level.archive', obj, ['status'])
        return redirect('admin:content_leveldefinition_change', object_id)

@admin.register(RuleSet)
class RuleAdmin(AuditedAdmin):
    form = RuleForm
    list_display = ('id', 'title', 'game')
    list_filter = ('game',)

    def get_changeform_initial_data(self, request):
        return {'game': request.GET.get('game', 'history')}

    def add_view(self, request, form_url='', extra_context=None):
        if request.method == 'GET' and (not request.GET.get('game')):
            return TemplateResponse(request, 'content/choose_rule.html', {**self.admin_site.each_context(request), 'title': 'Выберите механику приватной оценки'})
        return super().add_view(request, form_url, extra_context)

@admin.register(SpriteModule)
class ModuleAdmin(AuditedAdmin):
    form = ModuleForm
    list_display = ('id', 'title', 'kind', 'active')

@admin.register(SpriteAsset)
class AssetAdmin(AuditedAdmin):
    form = AssetForm
    list_display = ('id', 'title', 'kind', 'width', 'height', 'active')
    readonly_fields = ('image_preview', 'digest', 'pixel_width', 'pixel_height')
    fields = ('id', 'title', 'kind', 'upload', 'width', 'height', 'active', 'image_preview', 'digest', 'pixel_width', 'pixel_height')

    def image_preview(self, obj):
        return format_html('<img src="/api/game-assets/{}/" width="120" alt="">', obj.pk) if obj else ''

@admin.register(GameFamily)
class FamilyAdmin(AuditedAdmin):
    list_display = ('id', 'title', 'position', 'active')

@admin.register(LevelVersion)
class VersionAdmin(SnapshotAdmin):
    list_display = ('level', 'version', 'created_at')
    list_filter = ('level__family',)

@admin.register(CareerOffer)
class OfferAdmin(AuditedAdmin):
    form = OfferForm
    list_display = ('id', 'title', 'direction', 'published', 'archived')
    list_filter = ('published', 'archived')

@admin.register(PointReward)
class RewardAdmin(AuditedAdmin):
    form = RewardForm
    list_display = ('id', 'title', 'cost', 'stock', 'published', 'archived')

    def save_model(self, request, obj, form, change):
        services.save_reward(obj, request.user)

@admin.register(Material)
class MaterialAdmin(AuditedAdmin):
    form = MaterialForm
    list_display = ('id', 'title', 'category', 'audience', 'published', 'archived', 'version', 'points')
    list_filter = ('audience', 'category', 'published', 'archived')
    search_fields = ('id', 'title')
    readonly_fields = ('version_display', 'points_display', 'created_display', 'updated_display', 'archive_link', 'material_preview_link','compare_link')
    fields = ('id', 'title', 'description', 'category', 'audience', 'published', 'demo', 'blocks_editor', 'without_quiz', 'quiz', 'expected_version', 'version_display', 'points_display', 'material_preview_link','compare_link', 'archive_link', 'created_display', 'updated_display')

    @admin.display(description='Сравнение версий')
    def compare_link(self,obj):return format_html('<a href="{}">Сравнить версии материала и теста</a>',reverse('admin:content_material_compare',args=[obj.pk])) if obj and not obj._state.adding else 'После сохранения'

    def material_preview_link(self, obj):
        return format_html('<a href="{}">Предпросмотр материала и теста</a>', reverse('admin:content_material_preview', args=[obj.pk])) if obj and not obj._state.adding else 'Сначала сохраните черновик.'
    material_preview_link.short_description = 'Предпросмотр'

    def archive_link(self, obj):
        return format_html('<a href="{}">Архивация материала</a>', reverse('admin:content_material_archive', args=[obj.pk])) if obj and not obj._state.adding else 'Сначала сохраните черновик.'
    archive_link.short_description='Архивирование'

    @admin.display(description='Версия')
    def version_display(self,obj):return obj.version if not obj._state.adding else 'После сохранения'
    @admin.display(description='Баллы за тест')
    def points_display(self,obj):return obj.points if not obj._state.adding else 'Задаются в конструкторе теста'
    @admin.display(description='Создано')
    def created_display(self,obj):return obj.created_at if not obj._state.adding else 'После сохранения'
    @admin.display(description='Изменено')
    def updated_display(self,obj):return obj.updated_at if not obj._state.adding else 'После сохранения'

    def save_model(self, request, obj, form, change):
        services.save_material(obj, form.value, request.user, expected=form.expected)

    def get_urls(self):
        return [path('<path:object_id>/compare/',self.admin_site.admin_view(self.compare),name='content_material_compare'),path('<path:object_id>/preview/', self.admin_site.admin_view(self.preview), name='content_material_preview'), path('<path:object_id>/archive/', self.admin_site.admin_view(self.archive), name='content_material_archive')] + super().get_urls()

    def compare(self,request,object_id):
        obj=get_object_or_404(Material,pk=object_id)
        if not self.has_view_or_change_permission(request,obj) or not request.user.has_perm('core.view_materialversion'):raise PermissionDenied
        context=compare_context(request,obj.materialversion_set.order_by('version'),lambda version:json.loads(version.snapshot))
        if context is None:return HttpResponse(status=404)
        return TemplateResponse(request,'content/compare.html',{**self.admin_site.each_context(request),**context,'title':'Сравнение версий материала: '+obj.title,'back_url':reverse('admin:core_material_change',args=[obj.pk]),'private_visible':True})

    def preview(self, request, object_id):
        obj = get_object_or_404(Material, pk=object_id)
        if not self.has_view_or_change_permission(request, obj):
            raise PermissionDenied
        try:
            version = int(request.GET.get('version', obj.version))
        except ValueError:
            return HttpResponse(status=404)
        snapshot = get_object_or_404(MaterialVersion, material=obj, version=version)
        value = json.loads(snapshot.snapshot)
        questions = value.get('quiz', {}).get('questions', []) if value.get('quiz') else []
        checked = request.method == 'POST'
        correct = False
        if checked:
            correct = bool(questions) and all((request.POST.get('answer:' + q['id']) == q['correctOptionId'] for q in questions))
        return TemplateResponse(request, 'content/material_preview.html', {**self.admin_site.each_context(request), 'title': 'Предпросмотр: ' + obj.title, 'material': obj, 'value': value, 'questions': questions, 'version': version, 'checked': checked, 'correct': correct})

    def archive(self, request, object_id):
        obj = get_object_or_404(Material, pk=object_id)
        if not self.has_change_permission(request, obj):
            raise PermissionDenied
        if request.method == 'POST':
            if obj.pk == 'ochakovo-history':
                messages.error(request, 'Канонический материал истории нельзя архивировать.')
            else:
                obj.archived = 1
                obj.published = 0
                obj.save(update_fields=['archived', 'published'])
                services.audit(request.user, 'material.archive', obj, ['archived', 'published'])
            return redirect('admin:core_material_changelist')
        return TemplateResponse(request, 'content/archive.html', {**self.admin_site.each_context(request), 'title': 'Архивировать материал?', 'object': obj})

@admin.register(MaterialMedia)
class MediaAdmin(AuditedAdmin):
    form = MediaForm
    list_display = ('id', 'filename', 'mime_type', 'audience', 'size')
    readonly_fields = ('filename', 'mime_type', 'size', 'created', 'media_preview')

    def get_fields(self, request, obj=None):
        return ('id', 'audience', 'upload') if obj is None else ('id', 'filename', 'mime_type', 'audience', 'size', 'created', 'media_preview')

    def has_change_permission(self, request, obj=None):
        return obj is None and super().has_change_permission(request, obj)

    def get_changeform_initial_data(self, request):
        from uuid import uuid4
        return {'id': 'media-' + uuid4().hex, 'audience': 'candidate'}

    def get_urls(self):
        return [path('<path:object_id>/file/', self.admin_site.admin_view(self.file), name='content_media_file')] + super().get_urls()

    def file(self, request, object_id):
        if not self.has_view_permission(request):
            raise PermissionDenied
        obj = get_object_or_404(MaterialMedia, pk=object_id)
        response = HttpResponse(bytes(obj.content), content_type=obj.mime_type)
        response['X-Content-Type-Options'] = 'nosniff'
        response['Cache-Control'] = 'private, no-store'
        return response

    def media_preview(self, obj):
        url = reverse('admin:content_media_file', args=[obj.pk])
        return format_html('<video controls src="{}" style="max-width:500px"></video>', url) if obj.mime_type.startswith('video/') else format_html('<img src="{}" style="max-width:500px" alt="">', url)
for model in (MaterialVersion, MaterialQuestion, MaterialCompletion):
    admin.site.register(model, SnapshotAdmin)
