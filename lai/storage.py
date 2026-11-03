from pathlib import Path
from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible

@deconstructible
class PrivateStorage(FileSystemStorage):
    """Raiz separada de MEDIA_ROOT, inclusive no sistema integrado."""
    @property
    def base_location(self):
        return str(getattr(settings,'LAI_PRIVATE_ROOT',Path(settings.BASE_DIR)/'var'/'lai-private'))
    @property
    def location(self): return str(Path(self.base_location).resolve())
    def url(self,name): raise ValueError('Arquivo LAI privado: utilize a view autenticada de download.')

private_storage=PrivateStorage()
