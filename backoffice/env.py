"""Small environment loader; explicit process variables always take precedence."""
import os
import re
import shlex
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlsplit

from django.core.exceptions import ImproperlyConfigured


def load_environment(path):
    path = Path(path)
    if not path.is_file():
        return
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('export '):
            line = line[7:].strip()
        key, separator, value = line.partition('=')
        key = key.strip()
        if not separator or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', key):
            continue
        try:
            parts = shlex.split(value.strip(), comments=True, posix=True)
        except ValueError as error:
            raise ImproperlyConfigured('Некорректные кавычки в файле окружения.') from error
        os.environ.setdefault(key, ' '.join(parts))


def postgres_database(url):
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in ('postgres', 'postgresql') or not parsed.hostname or not parsed.path.strip('/'):
            raise ValueError()
        options = dict(parse_qsl(parsed.query, keep_blank_values=True))
        if 'connect_timeout' in options:
            options['connect_timeout'] = int(options['connect_timeout'])
        options.setdefault('connect_timeout', 10)
        return {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': unquote(parsed.path[1:]),
            'USER': unquote(parsed.username or ''),
            'PASSWORD': unquote(parsed.password or ''),
            'HOST': parsed.hostname,
            'PORT': str(parsed.port or 5432),
            'OPTIONS': options,
            'CONN_MAX_AGE': 60,
            'CONN_HEALTH_CHECKS': True,
        }
    except (AttributeError, TypeError, ValueError) as error:
        # Never include the URL: it may contain database credentials.
        raise ImproperlyConfigured('DATABASE_URL должен указывать на PostgreSQL: postgresql://…/database.') from error
