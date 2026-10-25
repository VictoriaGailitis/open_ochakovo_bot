import uuid
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class ImmutableRecord(models.Model):
    class Meta:
        abstract = True
    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError('Историческая запись неизменяема.')
        return super().save(*args, **kwargs)
    def delete(self, *args, **kwargs):
        raise ValidationError('Исторические записи не удаляются.')


class OperationsAudit(ImmutableRecord):
    created_at = models.DateTimeField(auto_now_add=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True)
    actor_name = models.CharField(max_length=150)
    action = models.CharField(max_length=100)
    entity = models.CharField(max_length=100)
    entity_id = models.CharField(max_length=200)
    reason = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    class Meta:
        ordering = ['-created_at', '-pk']
        verbose_name = 'Запись административного аудита'
        verbose_name_plural = 'Административный аудит'
        permissions = [
            ('view_candidate_pii', 'Просмотр анкет и контактов кандидатов'),
            ('export_candidate_data', 'Экспорт персональных данных откликов'),
            ('edit_candidate_profile', 'Исправление текущей анкеты с основанием'),
            ('manage_consent', 'Регистрация отзыва согласия'),
            ('anonymize_candidate', 'Обезличивание кандидата и снимков откликов'),
            ('manage_staff_accounts', 'Выдача и отключение аккаунтов мини-приложения'),
            ('manage_practice', 'Организация практики и назначения наставников'),
            ('view_private_checkins', 'Доступ к личным добровольным опросам практики'),
            ('view_career_preferences', 'Доступ к карьерным предпочтениям практикантов'),
            ('manage_events', 'Организация мероприятий и активностей'),
            ('view_activity_qr', 'Получение приватных QR-кодов активностей'),
            ('manage_referrals', 'Подтверждение найма по рефералке и выдачи мерча'),
            ('manage_fulfilment', 'Организация выдачи наград'),
            ('adjust_points', 'Обоснованные компенсирующие записи баллов'),
            ('revoke_api_sessions', 'Отзыв сессий мини-приложения'),
        ]
    def __str__(self):
        return f'{self.action}: {self.entity} {self.entity_id}'


class ConsentHistory(ImmutableRecord):
    user = models.ForeignKey('core.MiniUser', on_delete=models.PROTECT)
    recorded_at = models.DateTimeField(auto_now_add=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True)
    event = models.CharField(max_length=30, choices=[('observed', 'Сохранён исторический факт'), ('granted', 'Пользователь сохранил согласие'), ('revoked', 'Согласие отозвано'), ('anonymized', 'Данные обезличены')])
    consent = models.BooleanField(default=False)
    future_contact = models.BooleanField(default=False)
    original_consented_at = models.CharField(max_length=100, blank=True)
    policy_version = models.CharField(max_length=120, default='legacy-unversioned')
    reason = models.TextField()
    class Meta:
        ordering = ['-recorded_at', '-pk']
        verbose_name = 'История согласий'
        verbose_name_plural = 'История согласий'


class MentorAssignmentHistory(ImmutableRecord):
    practice = models.ForeignKey('core.Practice', on_delete=models.PROTECT)
    previous_mentor = models.ForeignKey('core.Mentor', on_delete=models.PROTECT, null=True, related_name='+')
    new_mentor = models.ForeignKey('core.Mentor', on_delete=models.PROTECT, null=True, related_name='+')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    reason = models.TextField()
    class Meta:
        ordering = ['-created_at', '-pk']
        verbose_name = 'Переназначение наставника'
        verbose_name_plural = 'История назначений наставников'


class LedgerAdjustment(ImmutableRecord):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey('core.MiniUser', on_delete=models.PROTECT)
    delta = models.IntegerField()
    reason = models.TextField()
    idempotency_key = models.UUIDField(default=uuid.uuid4, unique=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Компенсация баллов'
        verbose_name_plural = 'Компенсирующие операции баллов'
        constraints = [models.CheckConstraint(condition=~models.Q(delta=0), name='adjustment_nonzero')]


class Fulfilment(models.Model):
    exchange = models.OneToOneField('core.RewardExchange', on_delete=models.PROTECT, null=True, blank=True)
    referral_reward = models.OneToOneField('core.ReferralMerchReward', on_delete=models.PROTECT, null=True, blank=True)
    status = models.CharField(max_length=15, choices=[('pending', 'Подготовить'), ('ready', 'Готово к выдаче'), ('issued', 'Выдано')], default='pending')
    item = models.CharField('Что выдать', max_length=300)
    pickup = models.CharField('Место и порядок получения', max_length=500, blank=True)
    note = models.TextField('Комментарий организатора', blank=True)
    issued_at = models.DateTimeField(null=True, editable=False)
    issued_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        verbose_name = 'Выдача награды'
        verbose_name_plural = 'Выдача наград'
        constraints = [models.CheckConstraint(condition=(models.Q(exchange__isnull=False, referral_reward__isnull=True) | models.Q(exchange__isnull=True, referral_reward__isnull=False)), name='fulfilment_one_source')]
    def __str__(self):
        return f'{self.item} · {self.get_status_display()}'
