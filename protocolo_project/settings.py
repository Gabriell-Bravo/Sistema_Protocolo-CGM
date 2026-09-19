import os
import sys
from django.core.exceptions import ImproperlyConfigured
from pathlib import Path
from datetime import timedelta
from dotenv import load_dotenv
load_dotenv()


BASE_DIR = Path(__file__).resolve().parent.parent


def _env_bool(nome, padrao=False):
    return os.environ.get(nome, str(padrao)).strip().lower() in ('1', 'true', 'sim', 'yes')


def _env_lista(nome, padrao=''):
    return [item.strip() for item in os.environ.get(nome, padrao).split(',') if item.strip()]


EXECUTANDO_TESTES = len(sys.argv) > 1 and sys.argv[1] == 'test'

# item 62: padrão SEGURO. Produção roda com DEBUG desligado mesmo que a
# variável não seja definida. Para desenvolvimento local: DJANGO_DEBUG=True.
DEBUG = _env_bool('DJANGO_DEBUG', False)

SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY')
if not SECRET_KEY:
    if not (DEBUG or EXECUTANDO_TESTES):
        raise ImproperlyConfigured(
            'DJANGO_SECRET_KEY não definida. Defina a variável de ambiente '
            'no Portainer ou no ambiente do container.')
    SECRET_KEY = 'django-insecure-somente-para-desenvolvimento-local'

# Hosts e origens por variável de ambiente (separados por vírgula).
ALLOWED_HOSTS = _env_lista(
    'DJANGO_ALLOWED_HOSTS',
    '*' if DEBUG else 'controladoria.saquarema.rj.gov.br,localhost,127.0.0.1')
CSRF_TRUSTED_ORIGINS = _env_lista(
    'DJANGO_CSRF_TRUSTED_ORIGINS',
    'https://controladoria.saquarema.rj.gov.br,http://localhost:8800,'
    'http://127.0.0.1:8800,http://localhost:8000,http://127.0.0.1:8000')

# Atrás de proxy reverso com HTTPS (Nginx/Traefik/Portainer): DJANGO_HTTPS=True
if _env_bool('DJANGO_HTTPS', False):
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    USE_X_FORWARDED_PORT = True

X_FRAME_OPTIONS = 'DENY'
SECURE_CONTENT_TYPE_NOSNIFF = True
# O JavaScript das telas lê o cookie csrftoken (getCookie): NÃO marcar
# CSRF_COOKIE_HTTPONLY como True.
SESSION_COOKIE_HTTPONLY = True
# Sessão de um expediente (8 h). Ajustável por DJANGO_SESSAO_SEGUNDOS.
SESSION_COOKIE_AGE = int(os.environ.get('DJANGO_SESSAO_SEGUNDOS', 8 * 60 * 60))


INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'processos_app',
    'django.contrib.humanize',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    # Serve os arquivos de STATIC_ROOT sob gunicorn, onde o Django não os entrega sozinho.
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'protocolo_project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'processos_app.services.permissions.contexto_processor',
            ],
        },
    },
]

WSGI_APPLICATION = 'protocolo_project.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('POSTGRES_DB'),
        'USER': os.environ.get('POSTGRES_USER'),
        'PASSWORD': os.environ.get('POSTGRES_PASSWORD'),
        'HOST': os.environ.get('POSTGRES_HOST'),
        'PORT': os.environ.get('POSTGRES_PORT'),
    }
}

# If Postgres variables are not provided, fall back to the bundled sqlite DB for local development
if not (os.environ.get('POSTGRES_DB') and os.environ.get('POSTGRES_USER')):
    _pasta_sqlite = os.path.join(BASE_DIR, 'processos_app', 'database')
    os.makedirs(_pasta_sqlite, exist_ok=True)   # a pasta não é versionada (item 61)
    DATABASES['default'] = {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.path.join(_pasta_sqlite, 'protocolos.db'),
    }

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator', },
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', },
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator', },
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator', },
]

LANGUAGE_CODE = 'pt-br'
TIME_ZONE = 'America/Sao_Paulo'
USE_I18N = True
USE_TZ = True
# USE_L10N foi removido no Django 5.0 (localização é sempre ativa).

STATIC_URL = '/static/'
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static'), ]
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles_build')

STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage',
    },
}

WHITENOISE_USE_FINDERS = DEBUG


MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'mediafiles')


DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/login/'


# ---------------------------------------------------------------------------
# Logs no console do container (docker logs / Portainer). Erros inesperados
# das views são registrados aqui em vez de exibidos ao usuário (item 53).
# ---------------------------------------------------------------------------
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'padrao': {'format': '{asctime} {levelname} {name}: {message}', 'style': '{'},
    },
    'handlers': {
        'console': {'class': 'logging.StreamHandler', 'formatter': 'padrao'},
    },
    'root': {'handlers': ['console'], 'level': os.environ.get('DJANGO_LOG_LEVEL', 'INFO')},
    'loggers': {
        'django': {'handlers': ['console'], 'level': 'WARNING', 'propagate': False},
        'processos_app': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
    },
}
