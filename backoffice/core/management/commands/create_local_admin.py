"""Local-only review account; no password or account is shipped in source."""
import json,os,secrets
from pathlib import Path
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand,CommandError


class Command(BaseCommand):
    help='Создать локального администратора; сохранить данные только в игнорируемом файле.'

    def handle(self,*args,**options):
        if not settings.DEBUG or os.environ.get('DEV_AUTH')!='1':raise CommandError('Команда разрешена только локально при DEBUG и DEV_AUTH=1.')
        path=Path(settings.BASE_DIR)/'.data/django-local-admin.json'
        User=get_user_model()
        if path.exists():
            data=json.loads(path.read_text())
            if not User.objects.filter(username=data['username'],is_superuser=True).exists():raise CommandError('Файл доступа не соответствует базе; пароль не изменён.')
        else:
            username='local-admin'
            if User.objects.filter(username=username).exists():raise CommandError('Аккаунт уже есть; пароль не сброшен.')
            password=secrets.token_urlsafe(24)
            User.objects.create_superuser(username=username,email='local-admin@example.invalid',password=password)
            path.parent.mkdir(parents=True,exist_ok=True)
            fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'w') as f:json.dump({'username':username,'password':password},f)
        self.stdout.write('Локальный администратор готов. Данные входа: .data/django-local-admin.json (не Git).')
