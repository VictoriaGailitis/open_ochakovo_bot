"""Permission-scoped aggregate dashboard; never reads profiles or private check-ins."""
from django.contrib import admin
from django.db.models import Count
from django.urls import reverse

from backoffice.core import models as core
from backoffice.content import models as content


def visible_queryset(request, model):
    """Use the registered admin's complete permission and row-scope policy."""
    registered = admin.site._registry.get(model)
    if registered is None or not registered.has_view_permission(request):
        return None
    return registered.get_queryset(request)


def dashboard_callback(request, context):
    sections = []
    context.update(title='Рабочий стол', dashboard_sections=sections)
    if not request.user.is_active or not request.user.is_staff:
        return context

    def section(title, description):
        result = {'title': title, 'description': description, 'cards': [], 'statuses': []}
        sections.append(result)
        return result

    def metric(group, model, label, description, icon, **filters):
        queryset = visible_queryset(request, model)
        if queryset is None:
            return None
        value = queryset.filter(**filters).count()
        group['cards'].append({
            'label': label, 'description': description, 'value': value, 'icon': icon,
            'url': reverse(f'admin:{model._meta.app_label}_{model._meta.model_name}_changelist'),
        })
        return queryset

    hiring = section('Кандидаты и найм', 'Отклики, рекомендации и подтверждённые трудоустройства.')
    applications = metric(hiring, core.Application, 'Отклики', 'Все полученные заявки', 'work')
    if applications is not None:
        totals = {row['status']: row['total'] for row in applications.values('status').annotate(total=Count('id'))}
        hiring['statuses'] = [{'label': label, 'value': totals.get(status, 0)} for status, label in core.Application._meta.get_field('status').choices]
        known = {status for status, _ in core.Application._meta.get_field('status').choices}
        other = sum(value for status, value in totals.items() if status not in known)
        if other:
            hiring['statuses'].append({'label': 'Другие статусы', 'value': other})
    metric(hiring, core.ApplicationReferral, 'Рекомендации', 'Заявки с реферальной отметкой', 'person_add')
    metric(hiring, core.ReferralMerchReward, 'Мерч к выдаче', 'Найм подтверждён, мерч ещё не выдан', 'redeem', status='pending')
    metric(hiring, core.ReferralMerchReward, 'Мерч выдан', 'Завершённые реферальные вознаграждения', 'check_circle', status='issued')

    events = section('Мероприятия и активности', 'Публикация событий, запись участников и активности по QR.')
    metric(events, core.CareerEvent, 'Мероприятия', 'Опубликованные события', 'event', published=1)
    metric(events, core.EventActivity, 'Активности', 'Активные задания на мероприятиях', 'qr_code_scanner', active=1)
    metric(events, core.EventRegistration, 'Записи', 'Действующие регистрации', 'confirmation_number', status='registered')
    metric(events, core.ActivityCompletion, 'Участия в активностях', 'Подтверждения по QR за всё время', 'task_alt')

    learning = section('Материалы и игры', 'Содержание для участников и опубликованные игровые уровни.')
    metric(learning, core.Material, 'Материалы', 'Опубликованы и доступны своей аудитории', 'menu_book', published=1, archived=0)
    metric(learning, content.LevelDefinition, 'Уровни', 'Опубликованные игровые уровни', 'extension', status='published')
    metric(learning, content.LevelDefinition, 'Черновики уровней', 'Ожидают проверки и публикации', 'edit_note', status='draft')
    metric(learning, content.SpriteAsset, 'Спрайты', 'Активные элементы оформления', 'palette', active=True)

    practice = section('Сопровождение практики', 'Рабочие показатели без содержимого личных опросов.')
    metric(practice, core.Practice, 'Практики', 'Активные программы сопровождения', 'school', status='active')
    metric(practice, core.PracticeRequest, 'Обращения', 'Нерешённые обращения координатору', 'support_agent', status__in=['received', 'in_progress'])
    sections[:] = [group for group in sections if group['cards']]
    return context
