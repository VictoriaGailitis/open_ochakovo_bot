"""Prepare the shared PostgreSQL development database without resetting any data."""
import os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','backoffice.settings')
import django
django.setup()
from django.conf import settings
from django.core.management import call_command
from backoffice.core.models import MiniUser

call_command('migrate',interactive=False,verbosity=0)
source=Path(settings.BASE_DIR)/'.data/ochakovo.sqlite3'
if source.exists() and not MiniUser.objects.exists():
    call_command('import_sqlite',source=str(source))
call_command('bootstrap_miniapp',verbosity=0)
if settings.DEBUG and os.environ.get('DEV_AUTH')=='1':call_command('create_local_admin',verbosity=0)
