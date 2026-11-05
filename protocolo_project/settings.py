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
    'lai',  # Lei de Acesso à Informação: aba exclusiva do administrador
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
    # Nega /lai/ a quem não é administrador (valor de LAI_SOMENTE_ADMIN abaixo).
    'lai.middleware.SomenteAdministrador',
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
                'lai.context_processors.layout',
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


# ---------------------------------------------------------------------------
# Módulo LAI (Lei de Acesso à Informação): aba exclusiva do administrador.
# Tudo que ele grava (documentos, perfil do navegador do Fala.BR, pastas dos NUPs)
# fica em LAI_DATA_DIR, fora de MEDIA_ROOT e sem rota pública.
# ---------------------------------------------------------------------------
LAI_ENABLED = _env_bool('LAI_ENABLED', True)
# True: só superusuário acessa /lai/ (middleware lai.middleware) e o cadastro de Operador
# do administrador é criado sozinho na primeira visita. False: valem só as permissões lai.*.
LAI_SOMENTE_ADMIN = _env_bool('LAI_SOMENTE_ADMIN', True)
LAI_BASE_TEMPLATE = 'base.html'   # o módulo usa o layout (menu, tema) do protocolo
LAI_DATA_DIR = Path(os.environ.get('LAI_DATA_DIR', BASE_DIR / 'lai_dados'))
DATA_DIR = LAI_DATA_DIR            # usado por lai.navegador_falabr (perfil do navegador)
LAI_PRIVATE_ROOT = LAI_DATA_DIR / 'privado'
LAI_MAX_UPLOAD_BYTES = 15 * 1024 * 1024
LAI_SCANNER = os.environ.get('LAI_SCANNER', '')
LAI_PUBLIC_URL = os.environ.get('LAI_PUBLIC_URL', 'https://controladoria.saquarema.rj.gov.br/lai/')
# Envio das pastas dos NUPs ao Google Drive (conta de serviço). O JSON fica no servidor, fora do repositório.
LAI_DRIVE_CREDENCIAIS = os.environ.get('LAI_DRIVE_CREDENCIAIS', '')
LAI_DRIVE_PASTA_ID = os.environ.get('LAI_DRIVE_PASTA_ID', '')

# E-mail do módulo: SIMULADO até a TI homologar o SMTP (LAI_LIVE_EMAIL=1). O protocolo não envia e-mail.
LAI_LIVE_EMAIL = _env_bool('LAI_LIVE_EMAIL', False)
EMAIL_BACKEND = ('django.core.mail.backends.smtp.EmailBackend' if LAI_LIVE_EMAIL
                 else 'django.core.mail.backends.locmem.EmailBackend')
EMAIL_HOST = os.environ.get('LAI_SMTP_HOST', '')
EMAIL_PORT = int(os.environ.get('LAI_SMTP_PORT', '587'))
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.environ.get('LAI_SMTP_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('LAI_SMTP_PASSWORD', '')
EMAIL_TIMEOUT = 20
DEFAULT_FROM_EMAIL = os.environ.get('LAI_FROM_EMAIL', 'lai@example.invalid')

# Automação das pastas dos NUPs (só funciona no computador onde há Edge/Chrome com o Fala.BR logado).
# Para usar o Google Drive, aponte LAI_PASTA_ANO para a pasta sincronizada (Drive para computador).
LAI_PASTA_ANO = Path(os.environ.get('LAI_PASTA_ANO', LAI_DATA_DIR / 'pedidos' / '2026'))
LAI_PLANILHA_ATIVA = _env_bool('LAI_PLANILHA_ATIVA', False)   # desligada até definir o formato da planilha
LAI_PLANILHA_NOME = os.environ.get('LAI_PLANILHA_NOME', '2026 - CONTROLE FALA.BR.xlsx')
LAI_PLANILHA_ABA = os.environ.get('LAI_PLANILHA_ABA', 'FALA BR')
LAI_PLANILHA_MODO = os.environ.get('LAI_PLANILHA_MODO', 'copia')   # 'copia' (seguro) ou 'original' (com backup)
LAI_PLANILHA_DIAS_SECRETARIA = int(os.environ.get('LAI_PLANILHA_DIAS_SECRETARIA', '4'))
LAI_FALABR_BASE = os.environ.get('LAI_FALABR_BASE', 'https://falabr.cgu.gov.br').rstrip('/')
LAI_FALABR_CLIENT_ID = os.environ.get('LAI_FALABR_CLIENT_ID', '')
LAI_FALABR_CLIENT_SECRET = os.environ.get('LAI_FALABR_CLIENT_SECRET', '')
LAI_FALABR_USERNAME = os.environ.get('LAI_FALABR_USERNAME', '')
LAI_FALABR_PASSWORD = os.environ.get('LAI_FALABR_PASSWORD', '')