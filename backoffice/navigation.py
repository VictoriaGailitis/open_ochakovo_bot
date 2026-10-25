"""Build sidebar groups from Django's permission-filtered registered app list."""
from django.contrib import admin

GROUPS = [
    ('Кандидаты и команда', 'groups', {'MiniUser', 'Application', 'ApplicationReferral', 'ReferralCode', 'ReferralMerchReward', 'StaffCredential', 'Mentor', 'CareerOffer'}),
    ('Сопровождение практики', 'school', {'Practice', 'PracticeGoal', 'PracticeMeeting', 'PracticeFeedback', 'PracticeCheckin', 'PracticeRequest', 'PracticeCareer', 'PracticeActivity', 'MentorAssignmentHistory'}),
    ('Мероприятия и награды', 'event', {'CareerEvent', 'EventActivity', 'EventRegistration', 'ActivityCompletion', 'RewardExchange', 'Fulfilment', 'PointReward'}),
    ('Материалы', 'menu_book', {'Material', 'MaterialQuestion', 'MaterialVersion', 'MaterialCompletion', 'MaterialMedia'}),
    ('Игры и оформление', 'extension', {'GameFamily', 'LevelDefinition', 'LevelVersion', 'SpriteAsset', 'SpriteModule', 'LevelObject', 'RuleSet'}),
    ('Баллы и аудит', 'receipt_long', {'LedgerEntry', 'LedgerAdjustment', 'ConsentHistory', 'OperationsAudit', 'AnalyticsEvent'}),
    ('Системные данные', 'settings', {'ApiSession', 'GameProgress', 'PracticeMigration', 'StaffLoginAttempt', 'User', 'Group'}),
]


def sidebar(request):
    available = [model for app in admin.site.get_app_list(request) for model in app['models']]
    groups, used = [], set()
    for title, icon, names in GROUPS:
        items = []
        for index, model in enumerate(available):
            if model['object_name'] in names:
                link = model.get('admin_url') or model.get('add_url')
                if link:
                    items.append({'title': model['name'], 'icon': icon, 'link': link})
                    used.add(index)
        if items:
            groups.append({'title': title, 'separator': True, 'collapsible': True, 'items': items})
    remaining = [{'title': model['name'], 'icon': 'folder', 'link': model.get('admin_url') or model.get('add_url')}
                 for index, model in enumerate(available) if index not in used and (model.get('admin_url') or model.get('add_url'))]
    if remaining:
        groups.append({'title': 'Другие разделы', 'separator': True, 'collapsible': True, 'items': remaining})
    return groups
