"""Role-scoped Unfold operations. Historical facts never become editable forms."""
import io
import csv
import json
import secrets
from uuid import uuid4
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db import models as db_models
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html, format_html_join
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import action
from unfold.widgets import UnfoldAdminTextInputWidget, UnfoldAdminTextareaWidget
from backoffice.core import models as core
from . import forms, models, services


def uid(obj):
    return str(obj.user_id or '—')
uid.short_description='ID пользователя'


class OperationsAdmin(ModelAdmin):
    permission=None
    actions=None
    list_per_page=30
    def field_label(self,name):
        if name=='event':
            if self.model is core.AnalyticsEvent:return 'Событие аналитики'
            if self.model is core.PracticeActivity:return 'Действие'
            if self.model is models.ConsentHistory:return 'Тип записи согласия'
        return forms.FIELD_LABELS.get(name)
    def allowed(self,request):
        return not self.permission or request.user.has_perm('operations.'+self.permission)
    def has_view_permission(self,request,obj=None):return self.allowed(request) and super().has_view_permission(request,obj)
    def has_add_permission(self,request):return self.allowed(request) and super().has_add_permission(request)
    def has_change_permission(self,request,obj=None):return self.allowed(request) and super().has_change_permission(request,obj)
    def has_delete_permission(self,request,obj=None):return False
    def get_list_display(self,request):
        columns=[]
        for field in super().get_list_display(request):
            if not isinstance(field,str) or field not in forms.FIELD_LABELS:
                columns.append(field);continue
            model_field=self.model._meta.get_field(field)
            def localized(obj,name=field,relation=model_field.is_relation):
                display=getattr(obj,'get_'+name+'_display',None)
                if display:return display()
                value=getattr(obj,name)
                if isinstance(value,core.CareerEvent):return services.decode(value.definition,{}).get('title',str(value.pk))
                return str(value) if relation and value is not None else value
            localized.__name__='column_'+field
            localized.short_description=self.field_label(field)
            localized.admin_order_field=field
            columns.append(localized)
        return tuple(columns)
    def formfield_for_dbfield(self,db_field,request,**kwargs):
        if self.field_label(db_field.name):kwargs.setdefault('label',self.field_label(db_field.name))
        if isinstance(db_field,db_models.TextField) and not db_field.choices:
            kwargs.setdefault('widget',UnfoldAdminTextInputWidget() if db_field.name in forms.SINGLE_LINE_FIELDS else UnfoldAdminTextareaWidget(attrs={'rows':4}))
        return super().formfield_for_dbfield(db_field,request,**kwargs)
    def get_form(self,request,obj=None,change=False,**kwargs):
        form=super().get_form(request,obj,change,**kwargs)
        # Django's readonly renderer also honours ModelForm.Meta.labels.
        form._meta.labels={**(form._meta.labels or {}),**{name:self.field_label(name) for name in forms.FIELD_LABELS}}
        return form
    def formfield_for_foreignkey(self,db_field,request,**kwargs):
        if db_field.remote_field.model is core.MiniUser:kwargs['form_class']=forms.UserChoice
        return super().formfield_for_foreignkey(db_field,request,**kwargs)
    def save_model(self,request,obj,form,change):
        obj.save()
        services.audit(request.user,'record.updated' if change else 'record.created',obj,fields=form.changed_data)
    def changeform_view(self,request,object_id=None,form_url='',extra_context=None):
        try:return super().changeform_view(request,object_id,form_url,extra_context)
        except ValidationError as error:
            self.message_user(request,' '.join(error.messages),messages.ERROR)
            return redirect(request.path)
    def log_addition(self,request,obj,message):
        # Django's default log embeds str(object), which may contain a candidate name.
        return super().log_addition(request,obj,[]) if self.model is not core.MiniUser else None
    def log_change(self,request,obj,message):
        return super().log_change(request,obj,[]) if self.model is not core.MiniUser else None


class ReadOnlyAdmin(OperationsAdmin):
    def has_add_permission(self,request):return False
    def has_change_permission(self,request,obj=None):return False
    def get_readonly_fields(self,request,obj=None):
        return tuple(field.name for field in self.model._meta.fields if field.name not in ('password_hash','token','qr_token'))
    def get_fields(self,request,obj=None):return self.get_readonly_fields(request,obj)


@admin.register(core.MiniUser)
class MiniUserAdmin(OperationsAdmin):
    permission='view_candidate_pii'
    form=forms.ProfileForm
    list_display=('id','candidate_name','consent_status')
    search_fields=('id',)
    readonly_fields=('id','consent_facts','privacy_link')
    fields=('id','fullName','contact','birthDate','direction','availability','education','schedule','consent_facts','correction_reason','privacy_link')
    def get_queryset(self,request):return super().get_queryset(request).exclude(id__startswith='staff:')
    def has_add_permission(self,request):return False
    def has_change_permission(self,request,obj=None):
        return super().has_change_permission(request,obj) and request.user.has_perm('operations.edit_candidate_profile') and (obj is None or bool(services.decode(obj.profile,{}).get('consent')))
    @admin.display(description='Имя кандидата')
    def candidate_name(self,obj):return services.decode(obj.profile,{}).get('fullName','Анкета не заполнена')
    @admin.display(description='Согласие',boolean=True)
    def consent_status(self,obj):return bool(services.decode(obj.profile,{}).get('consent'))
    @admin.display(description='Исторический факт согласия')
    def consent_facts(self,obj):
        data=services.decode(obj.profile,{})
        return format_html('Обработка данных: {}; будущий контакт: {}; дата: {}. Исправление анкеты не меняет согласие.', 'Да' if data.get('consent') else 'Нет','Да' if data.get('futureContact') else 'Нет',data.get('consentedAt','Не зафиксирована'))
    @admin.display(description='Запрос субъекта данных')
    def privacy_link(self,obj):return format_html('<a href="{}">Отозвать согласие / обезличить</a>',reverse('admin:operations_candidate_privacy',args=[obj.pk]))
    def get_readonly_fields(self,request,obj=None):
        return ('id','profile_summary','consent_facts','privacy_link') if obj and not self.has_change_permission(request,obj) else super().get_readonly_fields(request,obj)
    def get_fields(self,request,obj=None):
        return self.get_readonly_fields(request,obj) if obj and not self.has_change_permission(request,obj) else self.fields
    @admin.display(description='Текущая анкета')
    def profile_summary(self,obj):
        return format_html('<dl>{}</dl>',format_html_join('','<dt>{}</dt><dd>{}</dd>',((key,value) for key,value in services.decode(obj.profile,{}).items() if key not in ('consent','futureContact','consentedAt'))))
    def save_model(self,request,obj,form,change):
        with transaction.atomic():
            old=core.MiniUser.objects.select_for_update().get(pk=obj.pk)
            old_profile=services.decode(old.profile,{})
            new_profile=services.decode(obj.profile,{})
            if not old_profile.get('consent'):raise ValidationError('Согласие отозвано. Обновите страницу.')
            for key in ('consent','futureContact','consentedAt'):new_profile[key]=old_profile.get(key)
            obj.profile=json.dumps(new_profile,ensure_ascii=False);obj.save(update_fields=['profile'])
            models.ConsentHistory.objects.create(user=obj,actor=request.user,event='observed',consent=bool(old_profile.get('consent')),future_contact=bool(old_profile.get('futureContact')),original_consented_at=old_profile.get('consentedAt',''),reason=form.cleaned_data['correction_reason'])
            services.audit(request.user,'candidate.corrected',obj,form.cleaned_data['correction_reason'],form.changed_data)
    def get_urls(self):return [path('<path:object_id>/privacy/',self.admin_site.admin_view(self.privacy_view),name='operations_candidate_privacy')]+super().get_urls()
    @method_decorator(csrf_protect)
    def privacy_view(self,request,object_id):
        obj=get_object_or_404(self.get_queryset(request),pk=object_id)
        if not self.has_view_permission(request,obj):raise PermissionDenied
        form=forms.PrivacyForm(request.POST or None)
        if request.method=='POST' and form.is_valid():
            try:services.privacy_action(actor=request.user,user=obj,**{key:form.cleaned_data[key] for key in ('action','reason')})
            except ValidationError as error:form.add_error(None,error)
            else:
                self.message_user(request,'Запрос обработан, сессии пользователя отозваны.')
                return redirect('admin:core_miniuser_change',object_id)
        return TemplateResponse(request,'admin/operations/operation_form.html',{**self.admin_site.each_context(request),'opts':self.model._meta,'title':'Запрос по персональным данным','description':'Отзыв завершает доступ к анкете. Обезличивание также очищает персональные поля в исторических откликах; журнал баллов сохраняется. Укажите основание запроса.','form':form,'object_id':object_id})


class ReferralFilter(admin.SimpleListFilter):
    title='Рекомендация сотрудника';parameter_name='referral'
    def lookups(self,request,model_admin):return [('yes','Есть рекомендация'),('no','Без рекомендации')]
    def queryset(self,request,queryset):
        if self.value()=='yes':return queryset.filter(applicationreferral__isnull=False)
        if self.value()=='no':return queryset.filter(applicationreferral__isnull=True)
        return queryset


@admin.register(core.Application)
class ApplicationAdmin(OperationsAdmin):
    permission='view_candidate_pii'
    list_display=('id',uid,'offer','status','referral_badge','created')
    list_filter=('status',ReferralFilter)
    search_fields=('id','user__id','offer')
    fields=('id','user_identity','offer','snapshot','referral_badge','status','created','hire_link')
    readonly_fields=('id','user_identity','offer','snapshot','referral_badge','created','hire_link')
    actions_list=('export_csv',)
    def has_export_candidate_permission(self,request):
        return self.has_view_permission(request) and request.user.has_perm('core.view_application') and request.user.has_perm('operations.export_candidate_data')
    def changelist_view(self,request,extra_context=None):
        response=super().changelist_view(request,extra_context)
        if hasattr(response,'context_data') and response.context_data:
            for item in response.context_data.get('actions_list',[]):
                if item.get('path') and request.GET:item['path']+='?'+request.GET.urlencode()
        return response
    @action(description='Скачать CSV по текущим фильтрам',permissions=['export_candidate'],url_path='export.csv',icon='download')
    def export_csv(self,request):
        if not self.has_export_candidate_permission(request):raise PermissionDenied
        if request.method!='GET':return HttpResponse(status=405,headers={'Allow':'GET'})
        from django.contrib.admin.options import IncorrectLookupParameters
        try:queryset=self.get_changelist_instance(request).queryset
        except IncorrectLookupParameters:return HttpResponse('Проверьте фильтры выгрузки.',status=400)
        applications=list(queryset.select_related('applicationreferral').order_by('created','pk')[:10001])
        if len(applications)>10000:return HttpResponse('В выгрузке более 10 000 откликов. Сузьте фильтры.',status=400)
        response=HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition']='attachment; filename="applications.csv"'
        response['Cache-Control']='private, no-store';response['X-Content-Type-Options']='nosniff'
        response.write('\ufeff')
        writer=csv.writer(response,quoting=csv.QUOTE_ALL)
        writer.writerow(['ID отклика','ID кандидата','Карьерное предложение','Статус','Создано','Имя и фамилия','Контакт','Дата рождения','Направление','Образование','Готовность начать','График','Согласие на обработку','Будущий контакт','Дата согласия','ID рекомендателя','Имя рекомендателя','Реферальный код'])
        def safe_cell(value):
            value='' if value is None else str(value)
            if value[:1] in ('\t','\r','\n') or value.lstrip(' \t\r\n\v\f\ufeff').startswith(('=','+','-','@')):value="'"+value
            return value
        for application in applications:
            profile=services.decode(application.profile,{})
            if not isinstance(profile,dict):profile={}
            referral=getattr(application,'applicationreferral',None)
            values=[application.pk,application.user_id,application.offer,application.get_status_display(),application.created,*[profile.get(key,'') for key in ('fullName','contact','birthDate','direction','education','availability','schedule')], 'Да' if profile.get('consent') is True else 'Нет','Да' if profile.get('futureContact') is True else 'Нет',profile.get('consentedAt',''),referral.referrer_user_id if referral else '',referral.referrer_name if referral else '',referral.code_id if referral else '']
            writer.writerow([safe_cell(value) for value in values])
        models.OperationsAudit.objects.create(actor=request.user,actor_name=request.user.get_username(),action='applications.exported',entity='core.application',entity_id='filtered-export',metadata={'application_ids':[str(application.pk) for application in applications],'count':len(applications)})
        return response
    def has_add_permission(self,request):return False
    @admin.display(description='ID кандидата')
    def user_identity(self,obj):return obj.user_id
    @admin.display(description='Снимок анкеты при отклике')
    def snapshot(self,obj):
        labels={'fullName':'Имя','contact':'Контакт','birthDate':'Дата рождения','direction':'Направление','availability':'Готовность начать','education':'Образование','schedule':'График','consent':'Согласие','futureContact':'Будущий контакт','consentedAt':'Дата согласия'}
        profile=services.decode(obj.profile,{})
        return format_html('<dl>{}</dl>',format_html_join('','<dt><strong>{}</strong></dt><dd>{}</dd>',((label,profile.get(key,'—')) for key,label in labels.items())))
    @admin.display(description='Рекомендация')
    def referral_badge(self,obj):
        referral=core.ApplicationReferral.objects.filter(application=obj).first()
        return format_html('<strong>★ Рекомендация сотрудника: {}</strong>',referral.referrer_name) if referral else '—'
    @admin.display(description='Подтверждение найма')
    def hire_link(self,obj):
        if not core.ApplicationReferral.objects.filter(application=obj).exists():return 'Нет реферальной рекомендации'
        return format_html('<a href="{}">Подтвердить состоявшийся найм</a>',reverse('admin:operations_application_hire',args=[obj.pk]))
    def get_urls(self):return [path('<path:object_id>/hire/',self.admin_site.admin_view(self.hire_view),name='operations_application_hire')]+super().get_urls()
    @method_decorator(csrf_protect)
    def hire_view(self,request,object_id):
        obj=get_object_or_404(self.get_queryset(request),pk=object_id)
        if not self.has_change_permission(request,obj) or not request.user.has_perm('operations.manage_referrals'):raise PermissionDenied
        if request.method=='POST':
            try:services.confirm_hire(actor=request.user,application=obj)
            except ValidationError as error:self.message_user(request,' '.join(error.messages),messages.ERROR)
            else:self.message_user(request,'Найм подтверждён. Рекомендовавшему сотруднику доступен мерч; баллы не начисляются.')
            return redirect('admin:core_application_change',object_id)
        return TemplateResponse(request,'admin/operations/confirm.html',{**self.admin_site.each_context(request),'opts':self.model._meta,'title':'Подтверждение найма','description':'Подтвердите, что кандидат действительно принят. Это создаст одно право рекомендателю на мерч без начисления баллов.','object_id':object_id})


@admin.register(core.StaffCredential)
class StaffAdmin(OperationsAdmin):
    permission='manage_staff_accounts';form=forms.StaffForm
    list_display=('login','role','active',uid)
    list_filter=('role','active');search_fields=('login','user__id')
    fields=('user_identity','login','role','active','staff_name','new_password')
    readonly_fields=('user_identity',)
    @admin.display(description='ID отдельного аккаунта мини-приложения')
    def user_identity(self,obj):return obj.user_id or 'Будет создан автоматически'
    def get_fields(self,request,obj=None):return ('user_identity','login','role','active') if obj and not self.has_change_permission(request,obj) else self.fields
    def save_model(self,request,obj,form,change):services.save_staff(actor=request.user,credential=obj,password=form.cleaned_data.get('new_password',''),name=form.cleaned_data.get('staff_name',''))


class ActivityInline(TabularInline):
    model=core.EventActivity;form=forms.ActivityForm;extra=0
    fields=('title','description','points','active','qr_link')
    readonly_fields=('qr_link',);can_delete=False
    def has_add_permission(self,request,obj=None):return request.user.has_perm('core.add_eventactivity') and request.user.has_perm('operations.manage_events')
    def has_change_permission(self,request,obj=None):return request.user.has_perm('core.change_eventactivity') and request.user.has_perm('operations.manage_events')
    @admin.display(description='QR-код')
    def qr_link(self,obj):return format_html('<a href="{}">Открыть QR</a>',reverse('admin:operations_activity_qr',args=[obj.pk])) if not obj._state.adding else 'После сохранения'


@admin.register(core.CareerEvent)
class EventAdmin(OperationsAdmin):
    permission='manage_events';form=forms.EventForm
    list_display=('event_title','event_date','audience','published','registered_count');list_filter=('audience','published')
    inlines=(ActivityInline,)
    fields=('title','description','date','startTime','location','type','capacity','program','requirements','audience','published','demo')
    readonly_fields=('event_details',)
    def get_fields(self,request,obj=None):return ('event_details','audience','published') if obj and not self.has_change_permission(request,obj) else self.fields
    @admin.display(description='Мероприятие')
    def event_details(self,obj):
        data=services.decode(obj.definition,{})
        return format_html('<dl>{}</dl>',format_html_join('','<dt><strong>{}</strong></dt><dd>{}</dd>',((key,', '.join(value) if isinstance(value,list) else value) for key,value in data.items() if key!='id')))
    @admin.display(description='Название')
    def event_title(self,obj):return services.decode(obj.definition,{}).get('title',obj.pk)
    @admin.display(description='Дата')
    def event_date(self,obj):return services.decode(obj.definition,{}).get('date','—')
    @admin.display(description='Записано')
    def registered_count(self,obj):return core.EventRegistration.objects.filter(event=obj,status='registered').count()
    def save_formset(self,request,form,formset,change):
        instances=formset.save(commit=False)
        for obj in instances:
            obj.save();services.audit(request.user,'event.activity.updated',obj,fields=formset.forms[0].changed_data if len(formset.forms)==1 else ())
        formset.save_m2m()


@admin.register(core.EventActivity)
class ActivityAdmin(OperationsAdmin):
    permission='manage_events';form=forms.ActivityForm
    list_display=('title','event','points','active','qr_link');list_filter=('active','event__audience')
    list_select_related=('event',)
    fields=('event','title','description','points','active','qr_link');readonly_fields=('qr_link',)
    @admin.display(description='Приватный QR-код')
    def qr_link(self,obj):return format_html('<a href="{}">Открыть / скачать / распечатать</a>',reverse('admin:operations_activity_qr',args=[obj.pk])) if not obj._state.adding else 'Появится после сохранения'
    def get_urls(self):return [path('<path:object_id>/qr/',self.admin_site.admin_view(self.qr_view),name='operations_activity_qr')]+super().get_urls()
    def qr_view(self,request,object_id):
        obj=get_object_or_404(self.get_queryset(request),pk=object_id)
        if not self.has_view_permission(request,obj) or not request.user.has_perm('operations.view_activity_qr'):raise PermissionDenied
        from server.app import ACTIVITY_QR_PREFIX
        import qrcode
        payload=ACTIVITY_QR_PREFIX+obj.qr_token
        kind=request.GET.get('format')
        if kind in ('png','svg'):
            output=io.BytesIO()
            if kind=='svg':
                from qrcode.image.svg import SvgPathImage
                qrcode.make(payload,image_factory=SvgPathImage,border=4).save(output)
            else:qrcode.make(payload,border=4).save(output,format='PNG')
            response=HttpResponse(output.getvalue(),content_type='image/svg+xml' if kind=='svg' else 'image/png')
            if request.GET.get('download')=='1':response['Content-Disposition']=f'attachment; filename="activity-qr.{kind}"'
        else:
            response=TemplateResponse(request,'admin/operations/qr.html',{**self.admin_site.each_context(request),'opts':self.model._meta,'title':'QR активности','activity':obj,'event_title':services.decode(obj.event.definition,{}).get('title',obj.event_id),'png_url':request.path+'?format=png','svg_url':request.path+'?format=svg&download=1'})
        response['Cache-Control']='private, no-store';response['X-Content-Type-Options']='nosniff'
        return response


@admin.register(core.EventRegistration)
class RegistrationAdmin(OperationsAdmin):
    permission='manage_events';form=forms.RegistrationForm
    list_display=('id',uid,'event','status','created');list_filter=('status','event__audience')
    readonly_fields=('id','created');fields=('id','user','event','status','created')
    search_fields=('id','user__id','event__id')


@admin.register(core.Mentor)
class MentorAdmin(OperationsAdmin):
    permission='manage_practice';form=forms.MentorForm;list_display=('name','position',uid)
    fields=('user','name','position','contact','about','office_hours')
    def formfield_for_foreignkey(self,db_field,request,**kwargs):
        if db_field.name=='user':kwargs['queryset']=core.MiniUser.objects.filter(staffcredential__active=1,staffcredential__role='mentor')
        return super().formfield_for_foreignkey(db_field,request,**kwargs)
    def save_model(self,request,obj,form,change):
        if not core.StaffCredential.objects.filter(user_id=obj.user_id,role='mentor',active=1).exists():raise ValidationError('Нужен активный аккаунт наставника.')
        if change and core.Mentor.objects.get(pk=obj.pk).user_id!=obj.user_id:raise ValidationError('Аккаунт существующего наставника неизменяем.')
        super().save_model(request,obj,form,change)


@admin.register(core.Practice)
class PracticeAdmin(OperationsAdmin):
    permission='manage_practice';form=forms.PracticeForm
    list_display=('title',uid,'mentor','department','start_date','end_date','status');list_filter=('status','department')
    fields=('user','mentor','title','department','start_date','end_date','status','coordinator_name','coordinator_contact','arrival','onboarding_lines','document_lines','assignment_reason')
    def has_change_permission(self,request,obj=None):return super().has_change_permission(request,obj) and (obj is None or obj.status not in ('completed','cancelled'))
    def get_fields(self,request,obj=None):
        return ('user','mentor','title','department','start_date','end_date','status','arrival','practice_summary') if obj and not self.has_change_permission(request,obj) else self.fields
    readonly_fields=('practice_summary',)
    @admin.display(description='Сведения о практике')
    def practice_summary(self,obj):
        coordinator=services.decode(obj.coordinator,{})
        documents=services.decode(obj.documents,[])
        return format_html('Координатор: {} · {}<br>Документы: {}<br>Первые шаги: {}',coordinator.get('name',''),coordinator.get('contact',''),'; '.join(f"{item.get('title','')}: {item.get('status','')}" for item in documents),', '.join(services.decode(obj.onboarding,[])))
    def save_model(self,request,obj,form,change):services.save_practice(actor=request.user,practice=obj,reason=form.cleaned_data['assignment_reason'])


class VersionedAdmin(OperationsAdmin):
    permission='manage_practice'
    def has_change_permission(self,request,obj=None):return super().has_change_permission(request,obj) and (obj is None or obj.practice.status not in ('completed','cancelled'))
    def get_fields(self,request,obj=None):return tuple(field for field in self.fields if field!='expected_version') if obj and not self.has_change_permission(request,obj) else self.fields
    def save_model(self,request,obj,form,change):
        if change:obj.version+=1
        else:obj.client_key='admin:'+str(uuid4())
        super().save_model(request,obj,form,change)


@admin.register(core.PracticeGoal)
class GoalAdmin(VersionedAdmin):
    form=forms.GoalForm;list_display=('title','practice','due_date','status','version');list_filter=('status',)
    fields=('practice','title','description','criteria','due_date','status','mentor_comment','expected_version')
    def has_change_permission(self,request,obj=None):return super().has_change_permission(request,obj) and (obj is None or obj.status!='approved')


@admin.register(core.PracticeMeeting)
class MeetingAdmin(VersionedAdmin):
    form=forms.MeetingForm;list_display=('title','practice','starts_at','ends_at','status');list_filter=('status',)
    fields=('practice','title','starts_at','ends_at','location','agenda','status','expected_version')
    def has_change_permission(self,request,obj=None):return super().has_change_permission(request,obj) and (obj is None or obj.status=='scheduled')


@admin.register(core.PracticeRequest)
class RequestAdmin(VersionedAdmin):
    form=forms.RequestForm;list_display=('topic','practice','status','created');list_filter=('status',)
    readonly_fields=('practice','topic','body','created')
    fields=('practice','topic','body','created','status','response','expected_version')
    def get_queryset(self,request):return super().get_queryset(request).filter(target='coordinator')
    def has_add_permission(self,request):return False
    def has_change_permission(self,request,obj=None):return super().has_change_permission(request,obj) and (obj is None or obj.status!='resolved')


@admin.register(models.LedgerAdjustment)
class AdjustmentAdmin(OperationsAdmin):
    permission='adjust_points';form=forms.AdjustmentForm
    list_display=('id',uid,'delta','reason','actor','created_at')
    fields=('user','delta','reason','idempotency_key')
    def has_change_permission(self,request,obj=None):return False
    def get_readonly_fields(self,request,obj=None):return tuple(field.name for field in self.model._meta.fields) if obj else ()
    def get_fields(self,request,obj=None):return self.get_readonly_fields(request,obj) if obj else self.fields
    def save_model(self,request,obj,form,change):
        saved=services.adjust_points(actor=request.user,user=form.cleaned_data['user'],delta=form.cleaned_data['delta'],reason=form.cleaned_data['reason'],idempotency_key=form.cleaned_data['idempotency_key'])
        obj.pk=saved.pk;obj.actor=request.user;obj.created_at=saved.created_at;obj._state.adding=False


@admin.register(models.Fulfilment)
class FulfilmentAdmin(OperationsAdmin):
    permission='manage_fulfilment';form=forms.FulfilmentForm
    list_display=('item','status','pickup','issued_at');list_filter=('status',)
    def has_change_permission(self,request,obj=None):return super().has_change_permission(request,obj) and (obj is None or obj.status!='issued')
    def save_model(self,request,obj,form,change):services.save_fulfilment(actor=request.user,fulfilment=obj)


@admin.register(core.ReferralCode)
class ReferralCodeAdmin(OperationsAdmin):
    permission='manage_referrals';list_display=('code',uid,'active','created');list_filter=('active',)
    readonly_fields=('code','user_identity','created');fields=('code','user_identity','active','created')
    def has_add_permission(self,request):return False
    @admin.display(description='ID рекомендателя')
    def user_identity(self,obj):return obj.user_id


@admin.register(core.ReferralMerchReward)
class ReferralRewardAdmin(ReadOnlyAdmin):
    permission='manage_referrals'
    list_display=('id','referrer_name','status','hired_at','issued_at');list_filter=('status',)


class PrivateCheckinAdmin(ReadOnlyAdmin):permission='view_private_checkins'
class CareerPreferencesAdmin(ReadOnlyAdmin):permission='view_career_preferences'
class PracticeHistoryAdmin(ReadOnlyAdmin):permission='manage_practice'
class ReferralHistoryAdmin(ReadOnlyAdmin):permission='manage_referrals'
class TechnicalAdmin(ReadOnlyAdmin):permission='revoke_api_sessions'


@admin.register(core.ApiSession)
class SessionAdmin(TechnicalAdmin):
    list_display=(uid,'expires','revoke_link')
    list_display_links=None
    fields=('user_identity','expires','revoke_link');readonly_fields=fields
    def get_readonly_fields(self,request,obj=None):return self.fields
    @admin.display(description='ID пользователя')
    def user_identity(self,obj):return obj.user_id
    @admin.display(description='Все сессии пользователя')
    def revoke_link(self,obj):return format_html('<a href="{}">Отозвать сессии</a>',reverse('admin:operations_revoke_sessions',args=[obj.user_id])) if obj.user_id else '—'
    def get_urls(self):return [path('user/<path:user_id>/revoke/',self.admin_site.admin_view(self.revoke_view),name='operations_revoke_sessions')]+super().get_urls()
    @method_decorator(csrf_protect)
    def revoke_view(self,request,user_id):
        if not self.has_view_permission(request):raise PermissionDenied
        user=get_object_or_404(core.MiniUser,pk=user_id)
        if request.method=='POST':
            services.revoke_sessions(actor=request.user,user=user)
            self.message_user(request,'Сессии отозваны.');return redirect('admin:core_apisession_changelist')
        return TemplateResponse(request,'admin/operations/confirm.html',{**self.admin_site.each_context(request),'opts':self.model._meta,'title':'Отзыв сессий','description':'Все действующие сессии этого пользователя будут завершены.','object_id':user_id})


@admin.register(core.StaffLoginAttempt)
class LoginAttemptAdmin(TechnicalAdmin):
    list_display=('failures','updated');list_display_links=None
    fields=('failures','updated')
    def get_readonly_fields(self,request,obj=None):return self.fields


for model, model_admin in [
    (core.LedgerEntry,ReadOnlyAdmin),(core.GameProgress,ReadOnlyAdmin),(core.ActivityCompletion,ReadOnlyAdmin),
    (core.RewardExchange,ReadOnlyAdmin),(core.AnalyticsEvent,TechnicalAdmin),
    (core.PracticeFeedback,PracticeHistoryAdmin),(core.PracticeActivity,PracticeHistoryAdmin),
    (core.PracticeCheckin,PrivateCheckinAdmin),(core.PracticeCareer,CareerPreferencesAdmin),
    (core.ApplicationReferral,ReferralHistoryAdmin),(core.PracticeMigration,TechnicalAdmin),
    (models.OperationsAudit,ReadOnlyAdmin),(models.ConsentHistory,ReadOnlyAdmin),(models.MentorAssignmentHistory,ReadOnlyAdmin),
]:
    admin.site.register(model,model_admin)
