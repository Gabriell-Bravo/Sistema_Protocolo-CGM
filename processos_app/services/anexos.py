"""Anexos do processo de Licitações e Contratos.

A análise, a pendência e o encaminhamento continuam no sistema e não são
exigidos para anexar. Quem pode ver o processo baixa o arquivo depois.
"""

import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from django.core.exceptions import ValidationError
from django.utils.html import escape

from . import permissions as perm
from .eventos import registrar_evento
from ..models import AnexoProcesso

EXTENSOES_PERMITIDAS = {
    '.pdf', '.png', '.jpg', '.jpeg', '.doc', '.docx',
    '.xls', '.xlsx', '.odt', '.ods', '.txt',
}
LIMITE_BYTES = 15 * 1024 * 1024
_W_NS = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'


def anexar(processo, usuario, arquivos):
    """Grava um ou mais arquivos. Devolve (salvos, erros de arquivo)."""
    perm.assert_permissao(
        perm.pode_anexar_arquivo(usuario, processo),
        'Somente o analista de Licitações e Contratos anexa arquivo neste processo.')

    if not arquivos:
        raise ValidationError('Selecione ao menos um arquivo.')

    salvos = []
    erros = []
    for arquivo in arquivos:
        try:
            salvos.append(_gravar(processo, usuario, arquivo))
        except ValidationError as exc:
            erros.extend(exc.messages)
    if not salvos and erros:
        raise ValidationError(erros)
    return salvos, erros


def remover(anexo_id, usuario):
    anexo = (AnexoProcesso.objects
             .select_related('processo')
             .get(pk=anexo_id))
    perm.assert_permissao(
        perm.pode_anexar_arquivo(usuario, anexo.processo),
        'Somente o analista de Licitações e Contratos remove arquivo deste processo.')

    nome = anexo.nome_original
    processo = anexo.processo
    if anexo.arquivo:
        anexo.arquivo.delete(save=False)
    anexo.delete()
    registrar_evento(
        processo, 'ARQUIVO_REMOVIDO', usuario,
        descricao=f'Arquivo removido: {nome}.',
        nome_arquivo=nome)
    return processo


def _gravar(processo, usuario, arquivo):
    nome = _nome_original(arquivo.name)
    extensao = Path(nome).suffix.lower()
    if extensao not in EXTENSOES_PERMITIDAS:
        raise ValidationError(
            f'"{nome}" não é um tipo permitido. Use PDF, Word, Excel, imagem ou texto.')
    if arquivo.size > LIMITE_BYTES:
        raise ValidationError(f'"{nome}" passa de 15 MB.')

    anexo = AnexoProcesso.objects.create(
        processo=processo,
        arquivo=arquivo,
        nome_original=nome,
        tamanho=arquivo.size or 0,
        enviado_por=usuario,
    )
    registrar_evento(
        processo, 'ARQUIVO_ANEXADO', usuario,
        descricao=f'Arquivo anexado: {nome}.',
        nome_arquivo=nome,
        anexo_id=anexo.id)
    return anexo


def _nome_original(nome):
    limpo = Path(nome or '').name.replace('\x00', '').strip()
    return (limpo or 'arquivo')[:255]


def html_preview_docx(anexo):
    """Converte .docx em HTML simples para preview no iframe.

    Extrai parágrafos do document.xml (sem dependência externa).
    .doc antigo (OLE) não é suportado — retorna None.
    """
    if anexo.extensao != '.docx' or not anexo.arquivo:
        return None
    try:
        with anexo.arquivo.open('rb') as handle:
            with zipfile.ZipFile(handle) as zf:
                with zf.open('word/document.xml') as xml_file:
                    raiz = ET.parse(xml_file).getroot()
    except (OSError, KeyError, zipfile.BadZipFile, ET.ParseError):
        return None

    blocos = []
    for paragrafo in raiz.iter(f'{_W_NS}p'):
        partes = []
        for no in paragrafo.iter(f'{_W_NS}t'):
            if no.text:
                partes.append(no.text)
            if no.tail:
                partes.append(no.tail)
        texto = ''.join(partes).strip()
        if texto:
            blocos.append(f'<p>{escape(texto)}</p>')
        else:
            blocos.append('<p><br></p>')

    corpo = '\n'.join(blocos) if blocos else '<p><em>(Documento sem texto legível)</em></p>'
    titulo = escape(anexo.nome_original or 'Documento Word')
    return (
        '<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8">'
        f'<title>{titulo}</title>'
        '<style>'
        'body{font-family:Segoe UI,Arial,sans-serif;font-size:15px;'
        'line-height:1.5;color:#0f172a;margin:16px 20px;max-width:900px;}'
        'p{margin:0 0 .75em;} em{color:#64748b;}'
        '</style></head><body>'
        f'{corpo}'
        '</body></html>'
    )
