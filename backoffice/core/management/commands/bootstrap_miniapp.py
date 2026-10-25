"""Seed only missing definitions; never replace edited content or user data."""
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group
import json
from server import community,learning
from server.app import CATALOG,now
from server.postgres import transaction


class Command(BaseCommand):
    help='Добавить отсутствующий стартовый контент и роли после migrate/import_sqlite.'

    def handle(self,*args,**options):
        call_command('seed_content',verbosity=options['verbosity'])
        with transaction() as db:
            community.seed(db,CATALOG)
            for event in CATALOG['events']:
                for activity in event.get('activities',[]):
                    from backoffice.core.models import EventActivity
                    EventActivity.objects.get_or_create(id=activity['id'],defaults={'event_id':event['id'],'title':activity['title'],'description':activity['description'],'points':activity['points'],'active':int(activity.get('active',True))})
            community.seed_activities(db)
            learning.seed(db)
            db.execute('INSERT OR IGNORE INTO practice_migrations VALUES(1,?)',(now(),))
        # Import historical consent facts without inventing a new consent or date.
        from backoffice.core.models import MiniUser
        from backoffice.operations.models import ConsentHistory
        for user in MiniUser.objects.exclude(profile__isnull=True).iterator():
            try:profile=json.loads(user.profile)
            except (ValueError,TypeError):continue
            if isinstance(profile,dict) and 'consent' in profile and not ConsentHistory.objects.filter(user=user).exists():
                ConsentHistory.objects.create(user=user,actor=None,event='observed',consent=profile.get('consent') is True,future_contact=profile.get('futureContact') is True,original_consented_at=str(profile.get('consentedAt','')),reason='Перенесён существующий факт из профиля прототипа; новое согласие не выдавалось.')
        if not Group.objects.exists():call_command('setup_backoffice_roles',verbosity=options['verbosity'])
        self.stdout.write(self.style.SUCCESS('Стартовые определения добавлены; существующий контент и награды сохранены.'))
