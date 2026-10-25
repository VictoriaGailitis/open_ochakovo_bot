"""PostgreSQL-only runtime and Russian Django Unfold backoffice."""
import os
import secrets
from pathlib import Path
from django.templatetags.static import static

from django.core.exceptions import ImproperlyConfigured

from .env import load_environment, postgres_database

BASE_DIR = Path(__file__).resolve().parent.parent
load_environment(BASE_DIR / '.env')
DEV_AUTH = os.environ.get('DEV_AUTH') == '1'
DEBUG = os.environ.get('DJANGO_DEBUG', '1' if DEV_AUTH else '0') == '1'

SECRET_KEY = os.environ.get('SECRET_KEY') or os.environ.get('DJANGO_SECRET_KEY', '')
if not SECRET_KEY and DEV_AUTH:
    secret_path = BASE_DIR / '.data' / 'django-secret'
    secret_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(secret_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        pass
    else:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as output:
            output.write(secrets.token_urlsafe(64))
    SECRET_KEY = secret_path.read_text(encoding='utf-8').strip()
if len(SECRET_KEY) < 50:
    raise ImproperlyConfigured('Задайте SECRET_KEY длиной не менее 50 символов.')

DATABASES = {'default': postgres_database(os.environ.get('DATABASE_URL', ''))}
if os.environ.get('DJANGO_TEST_DATABASE_NAME'):
    DATABASES['default']['TEST'] = {'NAME': os.environ['DJANGO_TEST_DATABASE_NAME']}
ALLOWED_HOSTS = [host.strip() for host in os.environ.get('DJANGO_ALLOWED_HOSTS', '127.0.0.1,localhost,[::1]').split(',') if host.strip()]
CSRF_TRUSTED_ORIGINS = [origin.strip() for origin in os.environ.get('CSRF_TRUSTED_ORIGINS', '').split(',') if origin.strip()]

INSTALLED_APPS = [
    'unfold',
    'unfold.contrib.filters',
    'unfold.contrib.forms',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'backoffice.core.apps.CoreConfig',
    'backoffice.operations',
    'backoffice.content',
]
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]
ROOT_URLCONF = 'backoffice.urls'
TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [BASE_DIR / 'backoffice' / 'templates'],
    'APP_DIRS': True,
    'OPTIONS': {'context_processors': [
        'django.template.context_processors.request',
        'django.contrib.auth.context_processors.auth',
        'django.contrib.messages.context_processors.messages',
    ]},
}]
WSGI_APPLICATION = 'backoffice.wsgi.application'
ASGI_APPLICATION = 'backoffice.asgi.application'
LANGUAGE_CODE = 'ru'
TIME_ZONE = 'Europe/Moscow'
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 12}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_SSL_REDIRECT = os.environ.get('DJANGO_SSL_REDIRECT', '0') == '1'
if os.environ.get('DJANGO_TRUST_PROXY') == '1':
    # Only enable behind our trusted reverse proxy; its port is not public.
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_HSTS_SECONDS = int(os.environ.get('DJANGO_HSTS_SECONDS', '0'))
X_FRAME_OPTIONS = 'DENY'
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / '.data' / 'static'
STATICFILES_DIRS = [directory for directory in [BASE_DIR / 'backoffice' / 'static'] if directory.is_dir()]
MEDIA_ROOT = BASE_DIR / '.data' / 'admin-media'
MEDIA_URL = '/protected-admin-media/'
DATA_UPLOAD_MAX_MEMORY_SIZE = 52 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024

UNFOLD = {
    'SCRIPTS': [lambda request: static('backoffice/navigation.js')],
    'SITE_TITLE': 'Очаково — управление',
    'SITE_HEADER': 'Очаково: изнутри',
    'SITE_SUBHEADER': 'Кабинет команды',
    'SITE_SYMBOL': 'factory',
    'SITE_URL': '/',
    'SHOW_HISTORY': True,
    'SHOW_VIEW_ON_SITE': False,
    'BORDER_RADIUS': '12px',
    'DASHBOARD_CALLBACK': 'backoffice.dashboard.dashboard_callback',
    'COLORS': {'primary': {
        '50': '#fff0f3', '100': '#ffdee6',
        '200': '#ffbdce', '300': '#ff8ba7',
        '400': '#f54f76', '500': '#d50032',
        '600': '#b5002b', '700': '#980024',
        '800': '#7b001d', '900': '#5e0016',
        '950': '#38000d',
    }},
    'SIDEBAR': {
        'show_search': True,
        'show_all_applications': True,
        'navigation': 'backoffice.navigation.sidebar',
    },
}
