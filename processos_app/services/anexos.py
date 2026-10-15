"""Anexos do processo de Licitações e Contratos.

A análise, a pendência e o encaminhamento continuam no sistema e não são
exigidos para anexar. Quem pode ver o processo baixa o arquivo depois.
"""

import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
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
    if anexo.arquivo_pdf:
        anexo.arquivo_pdf.delete(save=False)
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
    if extensao == '.docx':
        try:
            garantir_copia_pdf(anexo)
        except OSError:
            pass
    return anexo


def _nome_original(nome):
    limpo = Path(nome or '').name.replace('\x00', '').strip()
    return (limpo or 'arquivo')[:255]


def _texto_elemento(elemento):
    partes = []
    for no in elemento.iter(f'{_W_NS}t'):
        if no.text:
            partes.append(no.text)
        if no.tail:
            partes.append(no.tail)
    return ''.join(partes).strip()


def blocos_de_raiz(raiz):
    """Parágrafos e linhas de tabela, na ordem do documento."""
    body = raiz.find(f'{_W_NS}body')
    origem = list(body) if body is not None else list(raiz.iter(f'{_W_NS}p'))
    blocos = []
    for filho in origem:
        if filho.tag == f'{_W_NS}p':
            texto = _texto_elemento(filho)
            if texto:
                blocos.append(texto)
        elif filho.tag == f'{_W_NS}tbl':
            for linha in filho.findall(f'{_W_NS}tr'):
                celulas = []
                for celula in linha.findall(f'{_W_NS}tc'):
                    texto = _texto_elemento(celula)
                    if texto:
                        celulas.append(texto)
                if celulas:
                    blocos.append(' | '.join(celulas))
    if not blocos:
        for paragrafo in raiz.iter(f'{_W_NS}p'):
            texto = _texto_elemento(paragrafo)
            if texto:
                blocos.append(texto)
    return blocos


def ler_blocos_docx(anexo):
    """None se o .docx não puder ser lido. Lista (possivelmente vazia) se abrir."""
    if anexo.extensao != '.docx' or not anexo.arquivo:
        return None
    try:
        with anexo.arquivo.open('rb') as handle:
            with zipfile.ZipFile(handle) as zf:
                with zf.open('word/document.xml') as xml_file:
                    raiz = ET.parse(xml_file).getroot()
    except (OSError, KeyError, zipfile.BadZipFile, ET.ParseError):
        return None
    return blocos_de_raiz(raiz)


def html_preview_docx(anexo):
    """Converte .docx em HTML simples para preview no iframe.

    Extrai parágrafos do document.xml (sem dependência externa).
    .doc antigo (OLE) não é suportado — retorna None.
    """
    blocos = ler_blocos_docx(anexo)
    if blocos is None:
        return None
    if blocos:
        corpo = '\n'.join(f'<p>{escape(texto)}</p>' for texto in blocos)
    else:
        corpo = '<p><em>(Documento sem texto legível)</em></p>'
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


def _quebrar_linha(texto, largura=90):
    palavras = (texto or '').split()
    if not palavras:
        return []
    linhas = []
    atual = ''
    for palavra in palavras:
        while len(palavra) > largura:
            linhas.append(palavra[:largura])
            palavra = palavra[largura:]
        if not atual:
            atual = palavra
        elif len(atual) + 1 + len(palavra) <= largura:
            atual = f'{atual} {palavra}'
        else:
            linhas.append(atual)
            atual = palavra
    if atual:
        linhas.append(atual)
    return linhas


def _pdf_literal(texto):
    bruto = (texto or '').encode('cp1252', errors='replace')
    return b'(' + bruto.replace(b'\\', b'\\\\').replace(b'(', b'\\(').replace(b')', b'\\)') + b')'


def pdf_de_texto(blocos, titulo=''):
    """PDF simples (Helvetica) para o navegador mostrar o relatório."""
    linhas = []
    if titulo:
        linhas.extend(_quebrar_linha(titulo))
        linhas.append('')
    for bloco in blocos or []:
        linhas.extend(_quebrar_linha(bloco))
        linhas.append('')
    if not any(linha.strip() for linha in linhas):
        linhas = ['(Documento sem texto legível)']
    por_pagina = 48
    paginas = [linhas[i:i + por_pagina] for i in range(0, len(linhas), por_pagina)] or [linhas]

    objetos = []
    # 1 catalog, 2 pages, depois pares page/contents, por último a fonte.
    kids = []
    proximo = 3
    fluxos = []
    for linhas_pagina in paginas:
        page_id = proximo
        stream_id = proximo + 1
        proximo += 2
        kids.append(page_id)
        comandos = [b'BT', b'/F1 11 Tf', b'50 800 Td', b'14 TL']
        for linha in linhas_pagina:
            comandos.append(_pdf_literal(linha) + b' Tj T*')
        comandos.append(b'ET')
        fluxo = b'\n'.join(comandos)
        fluxos.append((page_id, stream_id, fluxo))

    fonte_id = proximo
    objetos.append(b'1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n')
    kids_ref = b' '.join(f'{n} 0 R'.encode() for n in kids)
    objetos.append(
        b'2 0 obj << /Type /Pages /Count ' + str(len(kids)).encode()
        + b' /Kids [' + kids_ref + b'] >> endobj\n')
    for page_id, stream_id, fluxo in fluxos:
        objetos.append(
            f'{page_id} 0 obj << /Type /Page /Parent 2 0 R '
            f'/MediaBox [0 0 595 842] /Contents {stream_id} 0 R '
            f'/Resources << /Font << /F1 {fonte_id} 0 R >> >> >> endobj\n'.encode()
        )
        objetos.append(
            f'{stream_id} 0 obj << /Length {len(fluxo)} >> stream\n'.encode()
            + fluxo + b'\nendstream endobj\n'
        )
    objetos.append(
        f'{fonte_id} 0 obj << /Type /Font /Subtype /Type1 '
        f'/BaseFont /Helvetica /Encoding /WinAnsiEncoding >> endobj\n'.encode()
    )

    corpo = b'%PDF-1.4\n'
    offsets = [0]
    for obj in objetos:
        offsets.append(len(corpo))
        corpo += obj
    xref = len(corpo)
    total = len(offsets)
    corpo += f'xref\n0 {total}\n'.encode()
    corpo += b'0000000000 65535 f \n'
    for offset in offsets[1:]:
        corpo += f'{offset:010d} 00000 n \n'.encode()
    corpo += (
        f'trailer << /Size {total} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF'.encode()
    )
    return corpo


def garantir_copia_pdf(anexo):
    """Grava a cópia PDF de um .docx. Devolve True se ela ficou disponível."""
    if anexo.extensao != '.docx':
        return bool(anexo.arquivo_pdf)
    if anexo.arquivo_pdf:
        try:
            if anexo.arquivo_pdf.storage.exists(anexo.arquivo_pdf.name):
                return True
        except OSError:
            pass
    blocos = ler_blocos_docx(anexo)
    if blocos is None:
        return False
    pdf = pdf_de_texto(blocos, anexo.nome_original or 'Relatório')
    nome = Path(anexo.nome_original or 'relatorio.docx').stem + '.pdf'
    anexo.arquivo_pdf.save(nome[:240], ContentFile(pdf), save=True)
    return True
