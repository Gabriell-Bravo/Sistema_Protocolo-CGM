"""Configuração temporária apenas para visualizar a interface localmente."""
import os

# settings.py exige DJANGO_SECRET_KEY fora do modo DEBUG; a pré-visualização
# é sempre local, então liga o DEBUG antes de importar.
os.environ.setdefault('DJANGO_DEBUG', 'True')

from .settings import *  # noqa: F401,F403

DEBUG = True
ALLOWED_HOSTS = ['*']

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.path.join(BASE_DIR, 'preview.sqlite3'),  # noqa: F405
    }
}
