import hashlib
import uuid
from io import BytesIO
from pathlib import Path
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.utils.module_loading import import_string
from pypdf import PdfReader
from PIL import Image
from .models import Documento

def validar(upload):
    if upload.size > getattr(settings, 'LAI_MAX_UPLOAD_BYTES', 15*1024*1024):
        raise ValidationError('Arquivo excede o limite de 15 MB.')
    data = upload.read()
    upload.seek(0)
    ext = Path(upload.name).suffix.lower()
    try:
        if ext == '.pdf':
            if not data.startswith(b'%PDF-'): raise ValueError()
            reader = PdfReader(BytesIO(data))
            if reader.is_encrypted or len(reader.pages) > 100: raise ValueError()
            root = reader.trailer['/Root']
            if '/OpenAction' in root or '/AA' in root or '/JavaScript' in root.get('/Names', {}):
                raise ValueError()
        elif ext in ('.jpg', '.jpeg', '.png'):
            with Image.open(BytesIO(data)) as im:
                if im.format not in ('JPEG', 'PNG'): raise ValueError()
                im.verify()
        else: raise ValueError()
    except Exception as exc: raise ValidationError('Use PDF sem conteúdo ativo ou imagem JPEG/PNG válida (até 100 páginas).') from exc
    scanner = getattr(settings, 'LAI_SCANNER', '')
    if scanner and not import_string(scanner)(data, upload.name):
        raise ValidationError('Arquivo reprovado pela verificação de segurança.')
    return data, ext

def guardar(demanda, upload, categoria, usuario, metadados=None):
    data, ext = validar(upload)
    doc = Documento(demanda=demanda, categoria=categoria, nome=Path(upload.name).name[:240],
        sha256=hashlib.sha256(data).hexdigest(), tamanho=len(data), usuario=usuario, metadados=metadados or {})
    doc.arquivo.save(f'{uuid.uuid4().hex}{ext}', ContentFile(data), save=False)
    doc.save()
    return doc
