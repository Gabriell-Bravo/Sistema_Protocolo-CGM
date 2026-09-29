"""Anexos do processo de Licitações e Contratos.

A análise, a pendência e o encaminhamento continuam no sistema e não são
exigidos para anexar. Quem pode ver o processo baixa o arquivo depois.
"""

from pathlib import Path

from django.core.exceptions import ValidationError

from . import permissions as perm
from .eventos import registrar_evento
from ..models import AnexoProcesso

EXTENSOES_PERMITIDAS = {
    '.pdf', '.png', '.jpg', '.jpeg', '.doc', '.docx',
    '.xls', '.xlsx', '.odt', '.ods', '.txt',
}
LIMITE_BYTES = 15 * 1024 * 1024


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
