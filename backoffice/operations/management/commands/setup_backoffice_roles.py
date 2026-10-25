"""Idempotent least-privilege groups, never provisioning Django auth users."""
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand
from django.db import transaction


def model_permissions(app,models,verbs=('view','add','change')):
    return {f'{app}.{verb}_{model.lower()}' for model in models for verb in verbs}


ROLE_PERMISSIONS={
    'HR':model_permissions('core',('MiniUser','Application','ReferralCode'),('view','change')) | model_permissions('core',('ApplicationReferral','ReferralMerchReward'),('view',)) | model_permissions('operations',('ConsentHistory',),('view',)) | {'operations.view_candidate_pii','operations.edit_candidate_profile','operations.manage_consent','operations.manage_referrals'},
    'organizer':model_permissions('core',('CareerEvent','EventActivity','EventRegistration')) | model_permissions('core',('ActivityCompletion','RewardExchange','ReferralMerchReward'),('view',)) | model_permissions('operations',('Fulfilment',)) | {'operations.manage_events','operations.view_activity_qr','operations.manage_fulfilment'},
    'coordinator':model_permissions('core',('Mentor','Practice','PracticeGoal','PracticeMeeting'),('view','add','change')) | model_permissions('core',('PracticeRequest',),('view','change')) | model_permissions('core',('PracticeFeedback','PracticeActivity'),('view',)) | model_permissions('operations',('MentorAssignmentHistory',),('view',)) | {'operations.manage_practice'},
    'technical_admin':model_permissions('core',('StaffCredential',)) | model_permissions('core',('ApiSession','StaffLoginAttempt','PracticeMigration','AnalyticsEvent','GameProgress','LedgerEntry'),('view',)) | model_permissions('operations',('OperationsAudit','LedgerAdjustment'),('view',)) | model_permissions('operations',('LedgerAdjustment',),('add',)) | {'operations.manage_staff_accounts','operations.revoke_api_sessions','operations.adjust_points'},
    'content_editor':model_permissions('core',('Material','MaterialMedia')) | model_permissions('core',('MaterialVersion','MaterialQuestion','MaterialCompletion'),('view',)) | model_permissions('content',('CareerOffer','PointReward')),
    'game_editor':model_permissions('content',('GameFamily','LevelDefinition','RuleSet','SpriteAsset','SpriteModule','LevelObject')) | model_permissions('content',('LevelVersion',),('view',)) | {'content.publish_leveldefinition'},
}


class Command(BaseCommand):
    help='Создать / обновить ограниченные группы админки без назначения пользователей и без прав Django auth.'
    @transaction.atomic
    def handle(self,*args,**options):
        available={f'{permission.content_type.app_label}.{permission.codename}':permission for permission in Permission.objects.select_related('content_type')}
        for name,keys in ROLE_PERMISSIONS.items():
            group,_=Group.objects.get_or_create(name=name)
            group.permissions.set([available[key] for key in sorted(keys) if key in available])
            missing=keys-available.keys()
            if missing:self.stderr.write(f'{name}: отсутствуют разрешения: '+', '.join(sorted(missing)))
            self.stdout.write(f'{name}: {group.permissions.count()} разрешений')
        self.stdout.write(self.style.SUCCESS('Группы настроены. Доступ к личным опросам, карьерным предпочтениям и обезличиванию назначается отдельно уполномоченным лицам.'))
