"""Human-facing editors over the legacy wire/storage representation."""
import json
from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo
from django import forms
from django.core.exceptions import ValidationError
from unfold.widgets import UnfoldAdminTextInputWidget, UnfoldAdminTextareaWidget, UnfoldAdminSelectWidget, UnfoldBooleanWidget
from backoffice.core import models as core
from . import services
from .models import Fulfilment, LedgerAdjustment


FIELD_LABELS={
    'id':'ID','user':'Пользователь','event':'Мероприятие','title':'Название','description':'Описание',
    'points':'Баллы','active':'Активен','login':'Логин','role':'Роль','name':'Имя','position':'Должность',
    'contact':'Контакт','about':'О наставнике','office_hours':'Время для связи','practice':'Практика',
    'mentor':'Наставник','department':'Подразделение','start_date':'Начало','end_date':'Окончание','status':'Статус',
    'arrival':'Как попасть на площадку','coordinator':'Координатор','onboarding':'Первые шаги','documents':'Документы',
    'criteria':'Критерии выполнения','due_date':'Срок','mentor_comment':'Комментарий наставника','version':'Версия',
    'starts_at':'Начало (Москва)','ends_at':'Окончание (Москва)','location':'Место','agenda':'Повестка',
    'target':'Кому адресовано','topic':'Тема','body':'Сообщение','response':'Ответ координатора',
    'audience':'Аудитория','published':'Опубликовано','created':'Создано','created_at':'Создано','updated':'Обновлено',
    'delta':'Изменение баллов','reason':'Основание','actor':'Администратор','actor_name':'Администратор',
    'exchange':'Обмен за баллы','referral_reward':'Право на мерч за рекомендацию','item':'Что выдать',
    'pickup':'Место и порядок получения','note':'Комментарий организатора','issued_at':'Выдано','issued_by':'Кем выдано',
    'idempotency_key':'Ключ операции','offer':'Карьерное предложение','reward':'Награда','code':'Реферальный код',
    'referrer_user':'Рекомендатель','referrer_name':'Имя рекомендателя','hired_candidate_user':'Принятый кандидат',
    'hired_at':'Найм подтверждён','hired_by':'Кем подтверждён найм','referral_code':'Реферальный код',
    'application':'Отклик','recorded_at':'Записано','consent':'Согласие на обработку данных','future_contact':'Будущий контакт',
    'original_consented_at':'Исходная дата согласия','policy_version':'Версия политики','metadata':'Метаданные',
    'previous_mentor':'Предыдущий наставник','new_mentor':'Новый наставник','entity':'Сущность','entity_id':'ID записи',
    'action':'Операция','completed_at':'Выполнено','awarded_points':'Начисленные баллы','activity':'Активность',
    'task':'Задание','draft':'Черновик','completed':'Первое завершение','draft_revision':'Версия черновика',
    'author_name':'Автор','answers':'Ответы','week':'Неделя','interested':'Интерес к работе','direction':'Направление',
    'schedule':'График','comment':'Комментарий','expires':'Действует до (Unix)','failures':'Неудачных попыток','applied':'Применено',
}
SINGLE_LINE_FIELDS={'title','login','name','position','contact','office_hours','department','location','topic','offer','reward','code','referral_code'}


class StyledFormMixin:
    """Keep native date/password semantics while using the installed Unfold theme."""
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        for name,field in self.fields.items():
            if name in FIELD_LABELS:field.label=FIELD_LABELS[name]
            widget=field.widget
            if name in SINGLE_LINE_FIELDS and isinstance(widget,forms.Textarea):
                field.widget=widget=UnfoldAdminTextInputWidget()
            if isinstance(widget,forms.Textarea):widget.attrs['rows']=4
            if widget.is_hidden or widget.attrs.get('class') or isinstance(widget,forms.CheckboxSelectMultiple):continue
            style=UnfoldBooleanWidget if isinstance(widget,forms.CheckboxInput) else UnfoldAdminTextareaWidget if isinstance(widget,forms.Textarea) else UnfoldAdminSelectWidget if isinstance(widget,forms.Select) else UnfoldAdminTextInputWidget
            widget.attrs['class']=style().attrs.get('class','')


class StyledModelForm(StyledFormMixin,forms.ModelForm):
    pass


class UserChoice(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return str(obj.pk)


class ProfileForm(StyledModelForm):
    fullName = forms.CharField(label='Имя и фамилия', max_length=300)
    contact = forms.CharField(label='Телефон или email', max_length=300)
    birthDate = forms.DateField(label='Дата рождения', widget=forms.DateInput(attrs={'type':'date'}, format='%Y-%m-%d'))
    direction = forms.ChoiceField(label='Направление', choices=[('undecided','Пока не определился'),('lab','Лаборатория и качество'),('production','Производство и розлив'),('technology','Пищевые технологии'),('warehouse','Склад и логистика'),('automation','Автоматизация'),('mechanics','Механика и оборудование')])
    availability = forms.CharField(label='Когда готов начать', max_length=300)
    education = forms.CharField(label='Образование', max_length=300)
    schedule = forms.CharField(label='График', required=False, max_length=300)
    correction_reason = forms.CharField(label='Основание исправления', widget=forms.Textarea)
    class Meta:
        model = core.MiniUser
        fields = ()
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        profile=services.decode(self.instance.profile,{})
        for name in ('fullName','contact','birthDate','direction','availability','education','schedule'):
            if name in self.fields:self.fields[name].initial=profile.get(name,'')
    def clean(self):
        data=super().clean()
        old=services.decode(self.instance.profile,{})
        if not old.get('consent') or str(self.instance.pk).startswith('staff:'):
            raise ValidationError('Исправлять можно только действующую анкету кандидата с согласием.')
        if self.errors: return data
        from server.app import API
        from server.errors import APIError
        payload={name:data[name] for name in ('fullName','contact','direction','availability','education','schedule')}
        payload.update(birthDate=data['birthDate'].isoformat(),consent=True,futureContact=bool(old.get('futureContact')))
        try: validated=API.profile(payload)
        except APIError as error: raise ValidationError(str(error))
        # Corrections cannot manufacture a new consent or change its historical time.
        self.instance.profile=json.dumps({**old,**{key:value for key,value in validated.items() if key not in ('consent','futureContact','consentedAt')}},ensure_ascii=False)
        return data


class StaffForm(StyledModelForm):
    staff_name=forms.CharField(label='Имя сотрудника',required=False,max_length=300,help_text='Можно изменить отображаемое имя. Пустое поле сохраняет текущее имя.')
    new_password=forms.CharField(label='Новый пароль',required=False,widget=forms.PasswordInput(render_value=False),help_text='Не менее 12 символов. Пустое поле сохраняет существующий пароль. Пароль не выводится и не хранится в журнале.')
    class Meta:
        model=core.StaffCredential
        fields=('login','role','active')
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        if not self.instance._state.adding and 'staff_name' in self.fields:
            self.fields['staff_name'].initial=services.decode(self.instance.user.profile,{}).get('fullName','')
    def clean(self):
        data=super().clean()
        if self.instance._state.adding:
            self.instance.user_id='staff:'+str(uuid4())
            if not data.get('new_password'): self.add_error('new_password','Для нового аккаунта нужен пароль.')
        if data.get('new_password') and len(data['new_password'])<12:
            self.add_error('new_password','Не менее 12 символов.')
        if data.get('role') not in ('intern','mentor','employee'): self.add_error('role','Недопустимая роль.')
        if not self.instance._state.adding:
            old=core.StaffCredential.objects.filter(pk=self.instance.pk).first()
            if old and old.role!=data.get('role') and (core.Practice.objects.filter(user_id=old.user_id).exclude(status__in=('completed','cancelled')).exists() or core.Practice.objects.filter(mentor__user_id=old.user_id).exclude(status__in=('completed','cancelled')).exists()):
                self.add_error('role','Сначала переназначьте или завершите действующие практики.')
        return data


class EventForm(StyledModelForm):
    title=forms.CharField(label='Название',max_length=200)
    description=forms.CharField(label='Описание',widget=forms.Textarea,max_length=10000)
    date=forms.DateField(label='Дата',widget=forms.DateInput(attrs={'type':'date'},format='%Y-%m-%d'))
    startTime=forms.TimeField(label='Начало (Москва)',input_formats=['%H:%M'],widget=forms.TimeInput(attrs={'type':'time'},format='%H:%M'))
    location=forms.CharField(label='Место',max_length=500)
    type=forms.CharField(label='Формат',max_length=100)
    capacity=forms.IntegerField(label='Вместимость',min_value=1,max_value=100000)
    program=forms.CharField(label='Программа — пункт на строку',widget=forms.Textarea,required=False)
    requirements=forms.CharField(label='Условия участия — пункт на строку',widget=forms.Textarea,required=False)
    demo=forms.BooleanField(label='Демонстрационное мероприятие',required=False)
    class Meta:
        model=core.CareerEvent
        fields=('audience','published')
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        value=services.decode(self.instance.definition,{})
        for field in ('title','description','date','startTime','location','type','capacity','demo','program','requirements'):
            if field in self.fields:self.fields[field].initial='\n'.join(value.get(field,[])) if field in ('program','requirements') else value.get(field,'')
    def clean(self):
        data=super().clean()
        if self.errors:return data
        if not self.instance._state.adding:
            old=core.CareerEvent.objects.select_for_update().get(pk=self.instance.pk)
            if old.audience!=data['audience'] and (core.EventRegistration.objects.filter(event=old).exists() or core.ActivityCompletion.objects.filter(activity__event=old).exists()):
                raise ValidationError('У мероприятия уже есть участники. Для другой аудитории создайте новое мероприятие.')
        if core.EventRegistration.objects.filter(event_id=self.instance.pk,status='registered').count()>data['capacity']:
            self.add_error('capacity','Вместимость меньше числа подтверждённых записей.')
            return data
        from server.community import _validate
        from server.errors import APIError
        payload={field:data[field] for field in ('title','description','location','type','capacity','demo','audience')}
        payload.update(date=data['date'].isoformat(),startTime=data['startTime'].strftime('%H:%M'),published=bool(data['published']),program=[line.strip() for line in data['program'].splitlines() if line.strip()],requirements=[line.strip() for line in data['requirements'].splitlines() if line.strip()])
        try: definition,_,_=_validate(payload)
        except APIError as error: raise ValidationError(str(error))
        definition['id']=self.instance.pk
        self.instance.definition=json.dumps(definition,ensure_ascii=False)
        return data


class ActivityForm(StyledModelForm):
    points=forms.IntegerField(label='Баллы',min_value=1,max_value=1000)
    class Meta:
        model=core.EventActivity
        fields=('event','title','description','points','active')
    def clean_event(self):
        event=self.cleaned_data['event']
        if not self.instance._state.adding and core.EventActivity.objects.get(pk=self.instance.pk).event_id!=event.pk:
            raise ValidationError('Нельзя переносить выданный QR в другое мероприятие.')
        return event


class RegistrationForm(StyledModelForm):
    user=UserChoice(queryset=core.MiniUser.objects.all(),label='ID пользователя')
    class Meta:
        model=core.EventRegistration
        fields=('user','event','status')
    def clean(self):
        data=super().clean()
        event,user=data.get('event'),data.get('user')
        if not event or not user:return data
        core.CareerEvent.objects.select_for_update().get(pk=event.pk)
        old=core.EventRegistration.objects.filter(pk=self.instance.pk).first()
        if old and (old.event_id!=event.pk or old.user_id!=user.pk):raise ValidationError('Пользователь и мероприятие записи неизменяемы.')
        if data.get('status')=='registered':
            definition=services.decode(event.definition,{})
            staff=core.StaffCredential.objects.filter(user=user,active=1).exists()
            if str(user.pk).startswith('staff:') and not staff:raise ValidationError('Учётная запись сотрудника отключена.')
            if not event.published or event.audience not in ('all','staff' if staff else 'candidate'):raise ValidationError('Мероприятие недоступно этому пользователю.')
            from server.app import moscow_today
            if definition.get('date','')<moscow_today().isoformat():raise ValidationError('Мероприятие уже прошло.')
            if not staff:
                from server.app import API
                from server.errors import APIError
                try:API.profile(services.decode(user.profile,{}))
                except APIError:raise ValidationError('Нужна действующая анкета кандидата старше 18 лет с согласием.')
            count=core.EventRegistration.objects.filter(event=event,status='registered').exclude(pk=self.instance.pk).count()
            if count>=definition.get('capacity',0):raise ValidationError('Свободных мест нет.')
        return data


class PracticeForm(StyledModelForm):
    user=UserChoice(queryset=core.MiniUser.objects.filter(staffcredential__active=1,staffcredential__role='intern'),label='Практикант (ID)')
    start_date=forms.DateField(label='Начало',widget=forms.DateInput(attrs={'type':'date'},format='%Y-%m-%d'))
    end_date=forms.DateField(label='Окончание',widget=forms.DateInput(attrs={'type':'date'},format='%Y-%m-%d'))
    coordinator_name=forms.CharField(label='Имя координатора',max_length=300)
    coordinator_contact=forms.CharField(label='Контакт координатора',max_length=300)
    onboarding_lines=forms.MultipleChoiceField(label='Выполненные первые шаги',required=False,choices=[('arrival','Прибытие'),('documents','Документы'),('safety','Техника безопасности'),('team','Знакомство с командой')],widget=forms.CheckboxSelectMultiple)
    document_lines=forms.CharField(label='Документы — Название | Статус на строку',required=False,widget=forms.Textarea)
    assignment_reason=forms.CharField(label='Основание назначения / изменения',widget=forms.Textarea)
    arrival=forms.CharField(label='Как попасть на площадку',required=False,max_length=2000,widget=forms.Textarea)
    class Meta:
        model=core.Practice
        fields=('user','mentor','title','department','start_date','end_date','status','arrival')
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        coordinator=services.decode(self.instance.coordinator,{})
        self.fields['coordinator_name'].initial=coordinator.get('name','')
        self.fields['coordinator_contact'].initial=coordinator.get('contact','')
        steps=services.decode(self.instance.onboarding,[])
        self.fields['onboarding_lines'].initial=steps
        self.fields['document_lines'].initial='\n'.join(f"{item.get('title',item.get('name',''))} | {item.get('status','Нужно подготовить')}" for item in services.decode(self.instance.documents,[]))
        if 'mentor' in self.fields:self.fields['mentor'].queryset=core.Mentor.objects.filter(user__staffcredential__active=1,user__staffcredential__role='mentor')
    def clean(self):
        data=super().clean()
        if self.errors:return data
        if data['end_date']<data['start_date']:raise ValidationError('Окончание раньше начала.')
        self.instance.start_date=data['start_date'].isoformat();self.instance.end_date=data['end_date'].isoformat()
        self.instance.coordinator=json.dumps({'name':data['coordinator_name'],'contact':data['coordinator_contact']},ensure_ascii=False)
        self.instance.onboarding=json.dumps(data['onboarding_lines'],ensure_ascii=False)
        documents=[]
        for line in data['document_lines'].splitlines():
            if not line.strip():continue
            parts=line.split('|',1)
            if len(parts)!=2 or not all(part.strip() for part in parts):raise ValidationError('Документ: Название | Статус.')
            documents.append({'id':'document-'+str(len(documents)+1),'title':parts[0].strip(),'status':parts[1].strip()})
        if len(documents)>20:raise ValidationError('Не более 20 документов.')
        self.instance.documents=json.dumps(documents,ensure_ascii=False)
        return data
    def save(self,commit=True):
        instance=super().save(commit=False)
        for field in ('start_date','end_date'):
            value=self.cleaned_data[field]
            setattr(instance,field,value.isoformat() if hasattr(value,'isoformat') else value)
        if commit:instance.save()
        return instance


class VersionedPracticeForm(StyledModelForm):
    expected_version=forms.IntegerField(widget=forms.HiddenInput,required=False)
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        if 'expected_version' in self.fields:self.fields['expected_version'].initial=self.instance.version
    def clean(self):
        data=super().clean()
        practice=data.get('practice') or getattr(self.instance,'practice',None)
        if practice:practice=core.Practice.objects.select_for_update().get(pk=practice.pk)
        if practice and practice.status in ('completed','cancelled'):raise ValidationError('Практика закрыта.')
        if not self.instance._state.adding:
            old=self._meta.model.objects.select_for_update().get(pk=self.instance.pk)
            if data.get('expected_version')!=old.version:raise ValidationError('Запись уже изменена. Обновите страницу.')
            if practice and old.practice_id!=practice.pk:raise ValidationError('Нельзя переносить запись в другую практику.')
        return data


class GoalForm(VersionedPracticeForm):
    due_date=forms.DateField(label='Срок',widget=forms.DateInput(attrs={'type':'date'},format='%Y-%m-%d'))
    mentor_comment=forms.CharField(label='Комментарий наставника',required=False,widget=forms.Textarea)
    class Meta:
        model=core.PracticeGoal
        fields=('practice','title','description','criteria','due_date','status','mentor_comment')
    def clean(self):
        data=super().clean();practice=data.get('practice');due=data.get('due_date')
        if practice and due and not practice.start_date<=due.isoformat()<=practice.end_date:raise ValidationError('Срок цели должен попадать в период практики.')
        old=core.PracticeGoal.objects.filter(pk=self.instance.pk).first() if not self.instance._state.adding else None
        allowed={'planned':('planned','in_progress'),'in_progress':('in_progress','review'),'review':('review','in_progress','approved'),'approved':()}
        if old and data.get('status') not in allowed.get(old.status,()):raise ValidationError('Недопустимый переход статуса цели; утверждённая цель неизменяема.')
        if not old and data.get('status')!='planned':raise ValidationError('Новая цель начинается со статуса «Запланирована».')
        return data
    def save(self,commit=True):
        instance=super().save(commit=False);instance.due_date=self.cleaned_data['due_date'].isoformat()
        if commit:instance.save()
        return instance


class MeetingForm(VersionedPracticeForm):
    starts_at=forms.DateTimeField(label='Начало (Москва)',widget=forms.DateTimeInput(attrs={'type':'datetime-local'},format='%Y-%m-%dT%H:%M'))
    ends_at=forms.DateTimeField(label='Окончание (Москва)',widget=forms.DateTimeInput(attrs={'type':'datetime-local'},format='%Y-%m-%dT%H:%M'))
    agenda=forms.CharField(label='Повестка',required=False,widget=forms.Textarea)
    class Meta:
        model=core.PracticeMeeting
        fields=('practice','title','starts_at','ends_at','location','agenda','status')
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        for field in ('starts_at','ends_at'):
            value=getattr(self.instance,field,'')
            if value and field in self.fields:
                try:self.fields[field].initial=datetime.fromisoformat(value.replace('Z','+00:00')).astimezone(ZoneInfo('Europe/Moscow'))
                except ValueError:pass
    def clean(self):
        data=super().clean();start,end=data.get('starts_at'),data.get('ends_at');practice=data.get('practice')
        if start and end:
            if end<=start:raise ValidationError('Окончание должно быть позже начала.')
            if practice and any(not practice.start_date<=value.astimezone(ZoneInfo('Europe/Moscow')).date().isoformat()<=practice.end_date for value in (start,end)):raise ValidationError('Встреча должна проходить в период практики.')
        old=core.PracticeMeeting.objects.filter(pk=self.instance.pk).first() if not self.instance._state.adding else None
        if old and old.status!='scheduled':raise ValidationError('Завершённая или отменённая встреча неизменяема.')
        return data
    def save(self,commit=True):
        instance=super().save(commit=False)
        for field in ('starts_at','ends_at'):setattr(instance,field,self.cleaned_data[field].isoformat())
        if commit:instance.save()
        return instance


class RequestForm(VersionedPracticeForm):
    response=forms.CharField(label='Ответ координатора',required=False,widget=forms.Textarea)
    class Meta:
        model=core.PracticeRequest
        fields=('status','response')
    def clean(self):
        data=super().clean()
        if self.instance.target!='coordinator':raise ValidationError('Ответы координатора доступны только в его входящих обращениях.')
        if data.get('status')=='resolved' and not data.get('response','').strip():self.add_error('response','Для решения обращения нужен ответ.')
        if not self.instance._state.adding:
            old=core.PracticeRequest.objects.get(pk=self.instance.pk)
            allowed={'received':('received','in_progress','resolved'),'in_progress':('in_progress','resolved'),'resolved':()}
            if data.get('status') not in allowed.get(old.status,()):raise ValidationError('Обращение уже решено или переход недопустим.')
        return data


class AdjustmentForm(StyledModelForm):
    user=UserChoice(queryset=core.MiniUser.objects.all(),label='ID пользователя')
    idempotency_key=forms.UUIDField(widget=forms.HiddenInput,initial=uuid4)
    class Meta:
        model=LedgerAdjustment
        fields=('user','delta','reason','idempotency_key')
    def clean_delta(self):
        delta=self.cleaned_data['delta']
        if not delta or abs(delta)>100000:raise ValidationError('Ненулевая сумма до 100 000 баллов.')
        return delta


class MentorForm(StyledModelForm):
    user=UserChoice(queryset=core.MiniUser.objects.filter(staffcredential__active=1,staffcredential__role='mentor'),label='Аккаунт наставника (ID)')
    about=forms.CharField(label='О наставнике',required=False,widget=forms.Textarea)
    office_hours=forms.CharField(label='Время для связи',required=False,max_length=300)
    class Meta:
        model=core.Mentor
        fields=('user','name','position','contact','about','office_hours')
    def clean_user(self):
        user=self.cleaned_data['user']
        if not self.instance._state.adding and core.Mentor.objects.get(pk=self.instance.pk).user_id!=user.pk:raise ValidationError('Нельзя менять аккаунт существующего наставника.')
        return user


class PrivacyForm(StyledFormMixin,forms.Form):
    action=forms.ChoiceField(label='Операция',choices=[('revoke','Отозвать согласие и сессии'),('anonymize','Обезличить анкету и снимки откликов')])
    reason=forms.CharField(label='Основание обращения',widget=forms.Textarea)
    confirm=forms.BooleanField(label='Подтверждаю выбранную операцию')


class FulfilmentForm(StyledModelForm):
    class Meta:
        model=Fulfilment
        fields=('exchange','referral_reward','status','item','pickup','note')
    def clean(self):
        data=super().clean()
        if bool(data.get('exchange'))==bool(data.get('referral_reward')):raise ValidationError('Выберите ровно один источник награды.')
        if not self.instance._state.adding and Fulfilment.objects.get(pk=self.instance.pk).status=='issued':raise ValidationError('Выдача уже зафиксирована.')
        return data
