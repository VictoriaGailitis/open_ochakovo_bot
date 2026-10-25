"""Permission-checked operational mutations. Callers never edit historical awards."""
import json
import re
import secrets
from datetime import datetime, timezone
from uuid import uuid4
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Sum
from backoffice.core import models as core
from .models import ConsentHistory, Fulfilment, LedgerAdjustment, MentorAssignmentHistory, OperationsAudit


def stamp():
    return datetime.now(timezone.utc).isoformat()


def require(actor, permission):
    if not actor.is_active or not actor.is_staff or not actor.has_perm('operations.' + permission):
        raise PermissionDenied


def audit(actor, action, obj, reason='', fields=()):
    return OperationsAudit.objects.create(actor=actor, actor_name=actor.get_username(), action=action,
        entity=obj._meta.label_lower, entity_id=str(obj.pk), reason=reason,
        metadata={'fields': [field for field in fields if field not in ('password_hash','new_password','qr_token','token','profile','answers')]})


def decode(value, default=None):
    try:
        return json.loads(value) if value else default
    except (TypeError, ValueError):
        return default


@transaction.atomic
def adjust_points(*, actor, user, delta, reason, idempotency_key):
    require(actor, 'adjust_points')
    if type(delta) is not int or delta == 0 or abs(delta) > 100000 or not isinstance(reason,str) or not reason.strip():
        raise ValidationError('Укажите ненулевую сумму до 100 000 баллов и основание.')
    from server.postgres import connect
    connect().lock('ledger-adjustment',idempotency_key)
    core.MiniUser.objects.select_for_update().get(pk=user.pk)
    existing = LedgerAdjustment.objects.filter(idempotency_key=idempotency_key).first()
    if existing:
        if (existing.user_id, existing.delta, existing.reason) != (user.pk, delta, reason.strip()):
            raise ValidationError('Этот ключ операции уже использован с другими параметрами.')
        return existing
    balance = core.LedgerEntry.objects.filter(user=user).aggregate(total=Sum('delta'))['total'] or 0
    if balance + delta < 0:
        raise ValidationError('Коррекция привела бы к отрицательному балансу.')
    operation = LedgerAdjustment.objects.create(user=user, delta=delta, reason=reason.strip(), idempotency_key=idempotency_key, actor=actor)
    core.LedgerEntry.objects.create(id=secrets.token_urlsafe(18), user=user, reason='adjustment:'+str(operation.pk), delta=delta, created=stamp())
    audit(actor, 'points.compensated', operation, reason.strip())
    return operation


@transaction.atomic
def save_staff(*, actor, credential, password='', name=''):
    require(actor, 'manage_staff_accounts')
    from server.staff_auth import password_hash
    credential.login = credential.login.strip().casefold()
    if not re.fullmatch(r'[a-z0-9][a-z0-9@._+-]{2,119}', credential.login):
        raise ValidationError('Проверьте логин.')
    if credential.role not in ('intern','mentor','employee') or credential.active not in (0,1) or not str(credential.user_id).startswith('staff:'):
        raise ValidationError('Нужна отдельная учётная запись сотрудника.')
    old = core.StaffCredential.objects.select_for_update().filter(pk=credential.pk).first()
    if old and old.role != credential.role:
        assigned = core.Practice.objects.filter(user_id=credential.user_id).exclude(status__in=('completed','cancelled')).exists()
        mentored = core.Practice.objects.filter(mentor__user_id=credential.user_id).exclude(status__in=('completed','cancelled')).exists()
        if assigned or mentored:
            raise ValidationError('Сначала завершите или переназначьте действующие практики, затем измените роль.')
    if not old and not password:
        raise ValidationError('Для новой учётной записи нужен пароль.')
    if password:
        try: credential.password_hash = password_hash(password)
        except ValueError as error: raise ValidationError(str(error))
    elif old:
        credential.password_hash = old.password_hash
    user, _ = core.MiniUser.objects.get_or_create(id=credential.user_id, defaults={'profile': json.dumps({'fullName':name.strip()},ensure_ascii=False) if name.strip() else None})
    renamed=False
    if old and name.strip():
        user=core.MiniUser.objects.select_for_update().get(pk=credential.user_id)
        profile=decode(user.profile,{})
        if not isinstance(profile,dict):profile={}
        if profile.get('fullName')!=name.strip():
            profile['fullName']=name.strip()
            user.profile=json.dumps(profile,ensure_ascii=False);user.save(update_fields=['profile']);renamed=True
    credential.user = user
    credential.save()
    if old and (password or not credential.active or credential.role != old.role or credential.login != old.login):
        core.ApiSession.objects.filter(user_id=credential.user_id).delete()
    audit(actor, 'staff.updated' if old else 'staff.provisioned', credential, fields=('login','role','active') + (('password_reset',) if password else ()) + (('staff_name',) if renamed else ()))
    return credential


@transaction.atomic
def revoke_sessions(*, actor, user):
    require(actor, 'revoke_api_sessions')
    core.MiniUser.objects.select_for_update().get(pk=user.pk)
    count, _ = core.ApiSession.objects.filter(user=user).delete()
    audit(actor, 'sessions.revoked', user, fields=('sessions',))
    return count


@transaction.atomic
def save_practice(*, actor, practice, reason):
    require(actor, 'manage_practice')
    if not reason.strip():raise ValidationError('Укажите основание назначения или изменения практики.')
    old = core.Practice.objects.select_for_update().filter(pk=practice.pk).first()
    if old and old.user_id != practice.user_id:
        raise ValidationError('Назначенную практику нельзя переносить другому пользователю.')
    if practice.status not in ('scheduled','active','completed','cancelled'):
        raise ValidationError('Недопустимый статус практики.')
    if old and old.status=='active' and practice.status=='scheduled':
        raise ValidationError('Начатую практику нельзя вернуть в запланированные.')
    if not core.StaffCredential.objects.filter(user_id=practice.user_id, role='intern', active=1).exists():
        raise ValidationError('Практику можно назначить активному практиканту.')
    if practice.mentor_id and not core.StaffCredential.objects.filter(user_id=practice.mentor.user_id, role='mentor', active=1).exists():
        raise ValidationError('Наставник должен иметь активную учётную запись наставника.')
    if practice.start_date > practice.end_date:
        raise ValidationError('Дата окончания раньше начала.')
    if old and old.status in ('completed','cancelled'):
        raise ValidationError('Завершённая или отменённая практика доступна только для чтения.')
    if core.PracticeGoal.objects.filter(practice_id=practice.pk).exclude(due_date__gte=practice.start_date,due_date__lte=practice.end_date).exists():
        raise ValidationError('Период не включает уже назначенные сроки целей.')
    from zoneinfo import ZoneInfo
    for meeting in core.PracticeMeeting.objects.filter(practice_id=practice.pk):
        dates=[datetime.fromisoformat(value.replace('Z','+00:00')).astimezone(ZoneInfo('Europe/Moscow')).date().isoformat() for value in (meeting.starts_at,meeting.ends_at)]
        if any(value < practice.start_date or value > practice.end_date for value in dates):
            raise ValidationError('Период не включает уже назначенные встречи.')
    practice.save()
    if not old or old.mentor_id != practice.mentor_id:
        MentorAssignmentHistory.objects.create(practice=practice,previous_mentor_id=old.mentor_id if old else None,new_mentor_id=practice.mentor_id,actor=actor,reason=reason)
    audit(actor, 'practice.updated' if old else 'practice.assigned', practice, reason)
    return practice


@transaction.atomic
def confirm_hire(*, actor, application):
    require(actor, 'manage_referrals')
    core.MiniUser.objects.select_for_update().get(pk=application.user_id)
    from server import referrals, postgres
    from server.errors import APIError
    try:
        with postgres.transaction() as db:
            result = referrals.mark_hired(db, str(application.pk), actor='django:'+str(actor.pk))
    except APIError as error:raise ValidationError(error.message) from error
    if not result['alreadyConfirmed']: audit(actor, 'referral.hire_confirmed', application)
    return result


@transaction.atomic
def issue_referral(*, actor, reward):
    require(actor, 'manage_referrals')
    core.MiniUser.objects.select_for_update().get(pk=reward.hired_candidate_user_id)
    from server import referrals, postgres
    from server.errors import APIError
    try:
        with postgres.transaction() as db:
            result = referrals.mark_reward_issued(db, str(reward.pk), actor='django:'+str(actor.pk))
    except APIError as error:raise ValidationError(error.message) from error
    if not result['alreadyIssued']: audit(actor, 'referral.merch_issued', reward)
    return result


@transaction.atomic
def save_fulfilment(*, actor, fulfilment):
    require(actor, 'manage_fulfilment')
    if bool(fulfilment.exchange_id) == bool(fulfilment.referral_reward_id):
        raise ValidationError('Выберите ровно один источник награды.')
    old = Fulfilment.objects.select_for_update().filter(pk=fulfilment.pk).first() if fulfilment.pk else None
    if old:
        if old.status == 'issued': raise ValidationError('Выдача уже зафиксирована и не редактируется.')
        if (old.exchange_id,old.referral_reward_id)!=(fulfilment.exchange_id,fulfilment.referral_reward_id): raise ValidationError('Источник выдачи нельзя менять.')
    source = fulfilment.exchange if fulfilment.exchange_id else fulfilment.referral_reward
    uid = source.user_id if fulfilment.exchange_id else source.referrer_user_id
    if fulfilment.referral_reward_id:
        # Match the API's candidate lock before touching the entitlement row.
        core.MiniUser.objects.select_for_update().get(pk=source.hired_candidate_user_id)
        source=core.ReferralMerchReward.objects.select_for_update().get(pk=source.pk)
        if source.status=='issued':raise ValidationError('Мерч по этому праву уже выдан. Повторная выдача недоступна.')
    core.MiniUser.objects.select_for_update().get(pk=uid)
    if fulfilment.status == 'issued':
        if fulfilment.referral_reward_id:
            # Fulfilment staff can issue an already-earned entitlement, never confirm a hire.
            from server import referrals, postgres
            with postgres.transaction() as db:
                referrals.mark_reward_issued(db,str(source.pk),actor='django:'+str(actor.pk))
        fulfilment.issued_at = datetime.now(timezone.utc)
        fulfilment.issued_by = actor
    fulfilment.save()
    audit(actor, 'reward.'+fulfilment.status, fulfilment)
    return fulfilment


@transaction.atomic
def privacy_action(*, actor, user, action, reason):
    if action not in ('revoke','anonymize'):raise ValidationError('Неизвестная операция с персональными данными.')
    require(actor, 'anonymize_candidate' if action == 'anonymize' else 'manage_consent')
    if not reason.strip(): raise ValidationError('Нужно основание операции.')
    locked = core.MiniUser.objects.select_for_update().get(pk=user.pk)
    if str(locked.pk).startswith('staff:'): raise ValidationError('Эта процедура предназначена для анкет кандидатов.')
    profile = decode(locked.profile,{})
    if not profile: raise ValidationError('У пользователя нет анкеты.')
    ConsentHistory.objects.create(user=locked,actor=actor,event='anonymized' if action=='anonymize' else 'revoked',consent=bool(profile.get('consent')),future_contact=bool(profile.get('futureContact')),original_consented_at=str(profile.get('consentedAt','')),reason=reason)
    if action == 'anonymize':
        private=('fullName','contact','birthDate','education','availability','schedule')
        def anonymize(value):
            result={key:val for key,val in value.items() if key not in private}
            result.update(fullName='Обезличенный пользователь',contact='',birthDate='',education='',availability='',schedule='')
            return result
        profile=anonymize(profile)
        for application in core.Application.objects.filter(user=locked).select_for_update():
            application.profile=json.dumps(anonymize(decode(application.profile,{})),ensure_ascii=False)
            application.save(update_fields=['profile'])
    profile.update(consent=False,futureContact=False)
    locked.profile=json.dumps(profile,ensure_ascii=False)
    locked.save(update_fields=['profile'])
    core.ApiSession.objects.filter(user=locked).delete()
    audit(actor,'privacy.'+action,locked,reason)
