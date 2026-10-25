"""Managed PostgreSQL models preserving the Mini App's legacy storage contract.

JSON and timestamps intentionally remain TEXT, integer flags remain INTEGER and
media content becomes PostgreSQL BYTEA. Composite legacy keys retain unique
constraints alongside admin-compatible surrogate IDs. Public serializers remain
in server modules and never expose credential or QR fields automatically.
"""
import json
import secrets
from datetime import datetime, timezone

from django.db import models


def new_id():
    return secrets.token_urlsafe(18)


def utc_stamp():
    return datetime.now(timezone.utc).isoformat()


def activity_qr_token():
    return secrets.token_urlsafe(32)


class LegacyModel(models.Model):
    class Meta:
        abstract = True

    def __str__(self):
        for field in ('title', 'name', 'code', 'login'):
            value = getattr(self, field, None)
            if value:
                return str(value)
        return str(self.pk)



class MiniUser(LegacyModel):
    id = models.TextField(primary_key=True)
    profile = models.TextField(null=True, blank=True)

    def __str__(self):
        # Foreign-key widgets and audit screens must not reveal profile names.
        return str(self.pk)


    class Meta:
        db_table = 'users'
        verbose_name = 'Пользователь приложения'
        verbose_name_plural = 'Пользователи приложения'


class ApiSession(LegacyModel):
    token = models.TextField(primary_key=True, editable=False)
    user = models.ForeignKey('MiniUser', on_delete=models.PROTECT, db_column='user_id', null=True, blank=True)
    expires = models.FloatField(null=True, blank=True)

    def __str__(self):
        return 'Сессия пользователя ' + str(self.user_id or '—')

    class Meta:
        db_table = 'sessions'
        verbose_name = 'Сессия API'
        verbose_name_plural = 'Сессии API'
        indexes = [
            models.Index(fields=['expires'], name='idx_sessions_expiry'),
        ]


class GameProgress(LegacyModel):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey('MiniUser', on_delete=models.PROTECT, db_column='user_id', null=True, blank=True)
    task = models.TextField(null=True, blank=True)
    draft = models.TextField(null=True, blank=True, default='{}', db_default='{}')
    completed = models.TextField(null=True, blank=True)
    draft_revision = models.BigIntegerField(default=0, db_default=0)

    class Meta:
        db_table = 'progress'
        verbose_name = 'Прогресс игры'
        verbose_name_plural = 'Прогресс игр'
        constraints = [
            models.UniqueConstraint(fields=['user', 'task'], name='uq_progress_0'),
        ]


class LedgerEntry(LegacyModel):
    id = models.TextField(primary_key=True, default=new_id)
    user = models.ForeignKey('MiniUser', on_delete=models.PROTECT, db_column='user_id', null=True, blank=True)
    reason = models.TextField(null=True, blank=True)
    delta = models.IntegerField(null=True, blank=True)
    created = models.TextField(null=True, blank=True, default=utc_stamp)

    class Meta:
        db_table = 'ledger'
        verbose_name = 'Запись баллов'
        verbose_name_plural = 'Журнал баллов'
        constraints = [
            models.UniqueConstraint(fields=['user', 'reason'], name='uq_ledger_1'),
        ]
        indexes = [
            models.Index(fields=['user'], name='idx_ledger_user'),
        ]


class Application(LegacyModel):
    id = models.TextField(primary_key=True, default=new_id)
    user = models.ForeignKey('MiniUser', on_delete=models.PROTECT, db_column='user_id', null=True, blank=True)
    offer = models.TextField(null=True, blank=True)
    profile = models.TextField(null=True, blank=True)
    status = models.TextField(null=True, blank=True, choices=[('sent', 'Отправлен'), ('reviewing', 'На рассмотрении'), ('contacted', 'HR связался'), ('accepted', 'Принят'), ('rejected', 'Завершён')])
    created = models.TextField(null=True, blank=True, default=utc_stamp)

    class Meta:
        db_table = 'applications'
        verbose_name = 'Отклик'
        verbose_name_plural = 'Отклики'
        constraints = [
            models.UniqueConstraint(fields=['user', 'offer'], name='uq_applications_0'),
        ]


class EventRegistration(LegacyModel):
    id = models.TextField(primary_key=True, default=new_id)
    user = models.ForeignKey('MiniUser', on_delete=models.PROTECT, db_column='user_id', null=True, blank=True)
    event = models.ForeignKey('CareerEvent', on_delete=models.PROTECT, db_column='event', null=True, blank=True)
    status = models.TextField(null=True, blank=True, choices=[('registered', 'Запись подтверждена'), ('cancelled', 'Отменена')])
    created = models.TextField(null=True, blank=True, default=utc_stamp)

    class Meta:
        db_table = 'registrations'
        verbose_name = 'Запись на мероприятие'
        verbose_name_plural = 'Записи на мероприятия'
        constraints = [
            models.UniqueConstraint(fields=['user', 'event'], name='uq_registrations_1'),
        ]
        indexes = [
            models.Index(fields=['event', 'status'], name='idx_registrations_event'),
        ]


class RewardExchange(LegacyModel):
    id = models.TextField(primary_key=True, default=new_id)
    user = models.ForeignKey('MiniUser', on_delete=models.PROTECT, db_column='user_id', null=True, blank=True)
    reward = models.TextField(null=True, blank=True)
    created = models.TextField(null=True, blank=True, default=utc_stamp)

    class Meta:
        db_table = 'exchanges'
        verbose_name = 'Обмен награды'
        verbose_name_plural = 'Обмены наград'
        constraints = [
            models.UniqueConstraint(fields=['user', 'reward'], name='uq_exchanges_1'),
        ]
        indexes = [
            models.Index(fields=['reward'], name='idx_exchanges_reward'),
        ]


class AnalyticsEvent(LegacyModel):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey('MiniUser', on_delete=models.PROTECT, db_column='user_id', null=True, blank=True)
    event = models.TextField(null=True, blank=True)
    created = models.TextField(null=True, blank=True, default=utc_stamp)

    class Meta:
        db_table = 'analytics'
        verbose_name = 'Аналитическое событие'
        verbose_name_plural = 'Аналитические события'


class EventActivity(LegacyModel):
    id = models.TextField(primary_key=True, default=new_id)
    event = models.ForeignKey('CareerEvent', on_delete=models.PROTECT, db_column='event_id')
    title = models.TextField()
    description = models.TextField()
    points = models.IntegerField()
    active = models.IntegerField(default=1, db_default=1, choices=[(0, 'Нет'), (1, 'Да')])
    qr_token = models.TextField(unique=True, default=activity_qr_token, editable=False)

    class Meta:
        db_table = 'event_activities'
        verbose_name = 'Активность мероприятия'
        verbose_name_plural = 'Активности мероприятий'
        constraints = [
            models.CheckConstraint(condition=models.Q(points__gte=1, points__lte=1000), name='ck_event_activities_0'),
            models.CheckConstraint(condition=models.Q(active__in=(0, 1)), name='ck_event_activities_1'),
        ]
        indexes = [
            models.Index(fields=['event', 'active'], name='idx_event_activities_event'),
        ]


class ActivityCompletion(LegacyModel):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey('MiniUser', on_delete=models.PROTECT, db_column='user_id')
    activity = models.ForeignKey('EventActivity', on_delete=models.PROTECT, db_column='activity_id')
    completed_at = models.TextField(default=utc_stamp)
    awarded_points = models.IntegerField()

    class Meta:
        db_table = 'activity_completions'
        verbose_name = 'Выполнение активности'
        verbose_name_plural = 'Выполнения активностей'
        constraints = [
            models.UniqueConstraint(fields=['user', 'activity'], name='uq_activity_completions_1'),
            models.CheckConstraint(condition=models.Q(awarded_points__gte=1, awarded_points__lte=1000), name='ck_activity_completions_0'),
        ]
        indexes = [
            models.Index(fields=['activity'], name='idx_activity_completion_c70ce0'),
        ]


class PracticeMigration(LegacyModel):
    version = models.IntegerField(primary_key=True)
    applied = models.TextField()

    class Meta:
        db_table = 'practice_migrations'
        verbose_name = 'Версия схемы практики'
        verbose_name_plural = 'Версии схемы практики'


class Mentor(LegacyModel):
    id = models.TextField(primary_key=True, default=new_id)
    user = models.OneToOneField('MiniUser', on_delete=models.PROTECT, db_column='user_id')
    name = models.TextField()
    position = models.TextField()
    contact = models.TextField()
    about = models.TextField(default='', db_default='')
    office_hours = models.TextField(default='', db_default='')

    class Meta:
        db_table = 'mentors'
        verbose_name = 'Наставник'
        verbose_name_plural = 'Наставники'


class Practice(LegacyModel):
    id = models.TextField(primary_key=True, default=new_id)
    user = models.ForeignKey('MiniUser', on_delete=models.PROTECT, db_column='user_id')
    mentor = models.ForeignKey('Mentor', on_delete=models.PROTECT, db_column='mentor_id', null=True, blank=True)
    title = models.TextField()
    department = models.TextField()
    start_date = models.TextField()
    end_date = models.TextField()
    status = models.TextField(choices=[('scheduled', 'Запланирована'), ('active', 'Идёт'), ('completed', 'Завершена'), ('cancelled', 'Отменена')])
    coordinator = models.TextField(default='{}', db_default='{}')
    arrival = models.TextField(default='', db_default='')
    onboarding = models.TextField(default='[]', db_default='[]')
    documents = models.TextField(default='[]', db_default='[]')
    created = models.TextField(default=utc_stamp)

    class Meta:
        db_table = 'practices'
        verbose_name = 'Назначение практики'
        verbose_name_plural = 'Назначения практики'
        constraints = [
            models.CheckConstraint(condition=models.Q(status__in=('scheduled', 'active', 'completed', 'cancelled')), name='ck_practices_0'),
            models.CheckConstraint(condition=models.Q(start_date__lte=models.F('end_date')), name='ck_practices_1'),
        ]
        indexes = [
            models.Index(fields=['mentor'], name='idx_practices_mentor'),
            models.Index(fields=['user', 'start_date'], name='idx_practices_user'),
        ]


class PracticeGoal(LegacyModel):
    id = models.TextField(primary_key=True, default=new_id)
    practice = models.ForeignKey('Practice', on_delete=models.PROTECT, db_column='practice_id')
    title = models.TextField()
    description = models.TextField()
    criteria = models.TextField()
    due_date = models.TextField()
    status = models.TextField(default='planned', db_default='planned', choices=[('planned', 'Запланирована'), ('in_progress', 'В работе'), ('review', 'На проверке'), ('approved', 'Подтверждена')])
    mentor_comment = models.TextField(default='', db_default='')
    version = models.IntegerField(default=1, db_default=1)
    client_key = models.TextField()

    class Meta:
        db_table = 'practice_goals'
        verbose_name = 'Цель практики'
        verbose_name_plural = 'Цели практики'
        constraints = [
            models.UniqueConstraint(fields=['practice', 'client_key'], name='uq_practice_goals_0'),
        ]


class PracticeMeeting(LegacyModel):
    id = models.TextField(primary_key=True, default=new_id)
    practice = models.ForeignKey('Practice', on_delete=models.PROTECT, db_column='practice_id')
    title = models.TextField()
    starts_at = models.TextField()
    ends_at = models.TextField()
    location = models.TextField()
    agenda = models.TextField()
    status = models.TextField(default='scheduled', db_default='scheduled', choices=[('scheduled', 'Запланирована'), ('completed', 'Завершена'), ('cancelled', 'Отменена')])
    version = models.IntegerField(default=1, db_default=1)
    client_key = models.TextField()

    class Meta:
        db_table = 'practice_meetings'
        verbose_name = 'Встреча'
        verbose_name_plural = 'Встречи'
        constraints = [
            models.UniqueConstraint(fields=['practice', 'client_key'], name='uq_practice_meetings_0'),
        ]


class PracticeFeedback(LegacyModel):
    id = models.TextField(primary_key=True, default=new_id)
    practice = models.ForeignKey('Practice', on_delete=models.PROTECT, db_column='practice_id')
    mentor = models.ForeignKey('Mentor', on_delete=models.PROTECT, db_column='mentor_id')
    author_name = models.TextField()
    body = models.TextField()
    created = models.TextField(default=utc_stamp)
    client_key = models.TextField()

    class Meta:
        db_table = 'practice_feedback'
        verbose_name = 'Отзыв наставника'
        verbose_name_plural = 'Отзывы наставников'
        constraints = [
            models.UniqueConstraint(fields=['practice', 'client_key'], name='uq_practice_feedback_0'),
        ]


class PracticeCheckin(LegacyModel):
    id = models.TextField(primary_key=True, default=new_id)
    practice = models.ForeignKey('Practice', on_delete=models.PROTECT, db_column='practice_id')
    week = models.TextField()
    answers = models.TextField()
    created = models.TextField(default=utc_stamp)

    class Meta:
        db_table = 'practice_checkins'
        verbose_name = 'Опрос практиканта'
        verbose_name_plural = 'Опросы практикантов'
        constraints = [
            models.UniqueConstraint(fields=['practice', 'week'], name='uq_practice_checkins_0'),
        ]


class PracticeRequest(LegacyModel):
    id = models.TextField(primary_key=True, default=new_id)
    practice = models.ForeignKey('Practice', on_delete=models.PROTECT, db_column='practice_id')
    target = models.TextField(choices=[('mentor', 'Наставнику'), ('coordinator', 'Координатору')])
    topic = models.TextField()
    body = models.TextField()
    status = models.TextField(default='received', db_default='received', choices=[('received', 'Получено'), ('in_progress', 'В работе'), ('resolved', 'Решено')])
    response = models.TextField(default='', db_default='')
    created = models.TextField(default=utc_stamp)
    version = models.IntegerField(default=1, db_default=1)
    client_key = models.TextField()

    class Meta:
        db_table = 'practice_requests'
        verbose_name = 'Обращение практиканта'
        verbose_name_plural = 'Обращения практикантов'
        constraints = [
            models.UniqueConstraint(fields=['practice', 'client_key'], name='uq_practice_requests_0'),
        ]


class PracticeCareer(LegacyModel):
    practice = models.OneToOneField('Practice', on_delete=models.PROTECT, db_column='practice_id', primary_key=True)
    interested = models.IntegerField()
    direction = models.TextField()
    schedule = models.TextField()
    comment = models.TextField()
    created = models.TextField(default=utc_stamp)

    class Meta:
        db_table = 'practice_career'
        verbose_name = 'Карьерный интерес'
        verbose_name_plural = 'Карьерные интересы'


class PracticeActivity(LegacyModel):
    id = models.TextField(primary_key=True, default=new_id)
    practice = models.ForeignKey('Practice', on_delete=models.PROTECT, db_column='practice_id')
    actor = models.ForeignKey('MiniUser', on_delete=models.PROTECT, db_column='actor_id')
    event = models.TextField()
    created = models.TextField(default=utc_stamp)

    class Meta:
        db_table = 'practice_activity'
        verbose_name = 'Событие практики'
        verbose_name_plural = 'Журнал практики'


class StaffCredential(LegacyModel):
    user = models.OneToOneField('MiniUser', on_delete=models.PROTECT, db_column='user_id', primary_key=True)
    login = models.TextField(unique=True)
    password_hash = models.TextField(editable=False)
    role = models.TextField(choices=[('intern', 'Практикант'), ('mentor', 'Наставник'), ('employee', 'Сотрудник')])
    active = models.IntegerField(default=1, db_default=1, choices=[(0, 'Нет'), (1, 'Да')])

    class Meta:
        db_table = 'staff_credentials'
        verbose_name = 'Выданная учётная запись'
        verbose_name_plural = 'Выданные учётные записи'
        constraints = [
            models.CheckConstraint(condition=models.Q(role__in=('intern', 'mentor', 'employee')), name='ck_staff_credentials_0'),
            models.CheckConstraint(condition=models.Q(active__in=(0, 1)), name='ck_staff_credentials_1'),
        ]


class StaffLoginAttempt(LegacyModel):
    key = models.TextField(primary_key=True)
    failures = models.IntegerField(default=0, db_default=0)
    updated = models.FloatField()

    def __str__(self):
        return 'Ограничение попыток входа'

    class Meta:
        db_table = 'staff_login_attempts'
        verbose_name = 'Ограничение входа'
        verbose_name_plural = 'Ограничения входа'


class Material(LegacyModel):
    id = models.TextField(primary_key=True, default=new_id)
    title = models.TextField()
    description = models.TextField()
    category = models.TextField(choices=[('company', 'О компании'), ('video', 'Видео'), ('practice', 'Практика'), ('stories', 'Истории')])
    audience = models.TextField(choices=[('candidate', 'Кандидатам'), ('staff', 'Сотрудникам'), ('all', 'Всем')])
    published = models.IntegerField(default=0, db_default=0, choices=[(0, 'Нет'), (1, 'Да')])
    archived = models.IntegerField(default=0, db_default=0, choices=[(0, 'Нет'), (1, 'Да')])
    blocks = models.TextField()
    points = models.IntegerField(default=0, db_default=0)
    version = models.IntegerField(default=1, db_default=1)
    demo = models.IntegerField(default=0, db_default=0, choices=[(0, 'Нет'), (1, 'Да')])
    created_at = models.TextField(default=utc_stamp)
    updated_at = models.TextField(default=utc_stamp)

    class Meta:
        db_table = 'materials'
        verbose_name = 'Материал'
        verbose_name_plural = 'Материалы'
        constraints = [
            models.CheckConstraint(condition=models.Q(category__in=('company', 'video', 'practice', 'stories')), name='ck_materials_0'),
            models.CheckConstraint(condition=models.Q(audience__in=('candidate', 'staff', 'all')), name='ck_materials_1'),
            models.CheckConstraint(condition=models.Q(published__in=(0, 1)), name='ck_materials_2'),
            models.CheckConstraint(condition=models.Q(archived__in=(0, 1)), name='ck_materials_3'),
            models.CheckConstraint(condition=models.Q(points__gte=0, points__lte=1000), name='ck_materials_4'),
        ]
        indexes = [
            models.Index(fields=['published', 'archived', 'audience', 'category'], name='idx_materials_visibility'),
        ]


class MaterialVersion(LegacyModel):
    id = models.BigAutoField(primary_key=True)
    material = models.ForeignKey('Material', on_delete=models.PROTECT, db_column='material_id')
    version = models.IntegerField()
    snapshot = models.TextField()
    created_at = models.TextField(default=utc_stamp)

    class Meta:
        db_table = 'material_versions'
        verbose_name = 'Версия материала'
        verbose_name_plural = 'Версии материалов'
        constraints = [
            models.UniqueConstraint(fields=['material', 'version'], name='uq_material_versions_0'),
        ]


class MaterialQuestion(LegacyModel):
    id = models.BigAutoField(primary_key=True, db_column='_pk')
    material = models.ForeignKey('Material', on_delete=models.PROTECT, db_column='material_id')
    version = models.IntegerField()
    question_id = models.TextField(db_column='id')
    position = models.IntegerField()
    text = models.TextField()
    options = models.TextField()
    correct_option_id = models.TextField()
    explanation = models.TextField()

    class Meta:
        db_table = 'material_questions'
        verbose_name = 'Вопрос материала'
        verbose_name_plural = 'Вопросы материалов'
        constraints = [
            models.UniqueConstraint(fields=['material', 'version', 'position'], name='uq_material_questions_0'),
            models.UniqueConstraint(fields=['material', 'version', 'question_id'], name='uq_material_questions_1'),
        ]


class MaterialCompletion(LegacyModel):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey('MiniUser', on_delete=models.PROTECT, db_column='user_id')
    material = models.ForeignKey('Material', on_delete=models.PROTECT, db_column='material_id')
    version = models.IntegerField()
    completed_at = models.TextField(default=utc_stamp)
    awarded_points = models.IntegerField()

    class Meta:
        db_table = 'material_completions'
        verbose_name = 'Прохождение материала'
        verbose_name_plural = 'Прохождения материалов'
        constraints = [
            models.UniqueConstraint(fields=['user', 'material'], name='uq_material_completions_0'),
        ]


class ReferralCode(LegacyModel):
    code = models.TextField(primary_key=True)
    user = models.OneToOneField('MiniUser', on_delete=models.PROTECT, db_column='user_id')
    active = models.IntegerField(default=1, db_default=1, choices=[(0, 'Нет'), (1, 'Да')])
    created = models.TextField(default=utc_stamp)

    class Meta:
        db_table = 'referral_codes'
        verbose_name = 'Реферальный код'
        verbose_name_plural = 'Реферальные коды'
        constraints = [
            models.CheckConstraint(condition=models.Q(active__in=(0, 1)), name='ck_referral_codes_0'),
        ]


class ApplicationReferral(LegacyModel):
    application = models.OneToOneField('Application', on_delete=models.PROTECT, db_column='application_id', primary_key=True)
    code = models.ForeignKey('ReferralCode', on_delete=models.PROTECT, db_column='code')
    referrer_user = models.ForeignKey('MiniUser', on_delete=models.PROTECT, db_column='referrer_user_id')
    referrer_name = models.TextField()
    created = models.TextField(default=utc_stamp)

    class Meta:
        db_table = 'application_referrals'
        verbose_name = 'Приглашение в отклике'
        verbose_name_plural = 'Приглашения в откликах'
        indexes = [
            models.Index(fields=['referrer_user'], name='idx_application_referra_a19adb'),
        ]


class ReferralMerchReward(LegacyModel):
    id = models.TextField(primary_key=True, default=new_id)
    application = models.OneToOneField('ApplicationReferral', on_delete=models.PROTECT, db_column='application_id')
    hired_candidate_user = models.OneToOneField('MiniUser', on_delete=models.PROTECT, db_column='hired_candidate_user_id', related_name='hiring_merch_reward')
    referrer_user = models.ForeignKey('MiniUser', on_delete=models.PROTECT, db_column='referrer_user_id')
    referrer_name = models.TextField()
    referral_code = models.TextField()
    status = models.TextField(default='pending', db_default='pending', choices=[('pending', 'Ожидает выдачи'), ('issued', 'Выдан')])
    hired_at = models.TextField()
    hired_by = models.TextField()
    issued_at = models.TextField(null=True, blank=True)
    issued_by = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'referral_merch_rewards'
        verbose_name = 'Мерч за трудоустройство'
        verbose_name_plural = 'Мерч за трудоустройство'
        constraints = [
            models.CheckConstraint(condition=models.Q(status__in=('pending', 'issued')), name='ck_referral_merch_rewards_0'),
            models.CheckConstraint(condition=(models.Q(status='pending', issued_at__isnull=True, issued_by__isnull=True) | models.Q(status='issued', issued_at__isnull=False, issued_by__isnull=False)), name='ck_referral_merch_rewards_1'),
        ]
        indexes = [
            models.Index(fields=['referrer_user', 'status'], name='idx_referral_merch_referrer'),
        ]


class CareerEvent(LegacyModel):
    id = models.TextField(primary_key=True, default=new_id)
    definition = models.TextField()
    audience = models.TextField(choices=[('candidate', 'Кандидатам'), ('staff', 'Сотрудникам'), ('all', 'Всем')])
    published = models.IntegerField(choices=[(0, 'Нет'), (1, 'Да')])

    def __str__(self):
        try:
            definition = json.loads(self.definition)
        except (TypeError, ValueError):
            return str(self.pk)
        if not isinstance(definition, dict):
            return str(self.pk)
        title = definition.get('title')
        date = definition.get('date')
        if not isinstance(title, str) or not title.strip():
            return str(self.pk)
        return title + (' · ' + date if isinstance(date, str) and date else '')

    class Meta:
        db_table = 'career_events'
        verbose_name = 'Мероприятие'
        verbose_name_plural = 'Мероприятия'
        constraints = [
            models.CheckConstraint(condition=models.Q(audience__in=('candidate', 'staff', 'all')), name='ck_career_events_0'),
            models.CheckConstraint(condition=models.Q(published__in=(0, 1)), name='ck_career_events_1'),
        ]


class MaterialMedia(LegacyModel):
    id = models.TextField(primary_key=True, default=new_id)
    filename = models.TextField()
    mime_type = models.TextField()
    audience = models.TextField(choices=[('candidate', 'Кандидатам'), ('staff', 'Сотрудникам'), ('all', 'Всем')])
    size = models.IntegerField()
    content = models.BinaryField(editable=False)
    created = models.TextField(default=utc_stamp)

    class Meta:
        db_table = 'material_media'
        verbose_name = 'Медиафайл'
        verbose_name_plural = 'Медиафайлы'
        constraints = [
            models.CheckConstraint(condition=models.Q(audience__in=('candidate', 'staff', 'all')), name='ck_material_media_0'),
            models.CheckConstraint(condition=models.Q(size__gt=0), name='ck_material_media_1'),
        ]
