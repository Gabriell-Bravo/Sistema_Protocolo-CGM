"""Linha de controle de cada pedido na planilha `2026 - CONTROLE FALA.BR.xlsx`.

Aba `FALA BR`, a partir da linha 4, uma linha por NUP:

    A NUP | B RECEBIDO | C OBJETO | D PRAZO FINAL BR | E ENVIADO PARA | F PRAZO DA SECRETARIA
    G RETORNO | H ENVIO NO PORTAL | I STATUS | J OBSERVAÇÃO

Este módulo preenche A, B, C, D, F e I (STATUS = AGUARDA) e deixa E, G, H e J em branco.
Linha de NUP que já existe não é alterada, exceto a coluna OBJETO quando o usuário editou o tema
no módulo. Por padrão grava numa cópia da planilha.
"""
import logging
import shutil
from copy import copy
from datetime import datetime, timedelta
from pathlib import Path

from django.conf import settings

from .pastas_pedidos import so_digitos, tema_para_texto

log = logging.getLogger(__name__)

PRIMEIRA_LINHA = 4
COLUNAS = 10
STATUS_INICIAL = 'AGUARDA'
LIMITE_VARREDURA = 20000


class PlanilhaErro(Exception):
    pass


def caminho():
    """Arquivo que será gravado: a cópia (padrão) ou o original."""
    base = Path(settings.LAI_PASTA_ANO)
    original = base / settings.LAI_PLANILHA_NOME
    if settings.LAI_PLANILHA_MODO == 'original':
        return original
    copia = original.with_name(f'{original.stem} - COPIA{original.suffix}')
    if not copia.exists() and original.exists():
        shutil.copy2(original, copia)
    return copia


def adicionar(linhas):
    """Acrescenta as linhas novas. `linhas` = [{'nup','cadastro','tema','prazo'}].

    Devolve ({nup: {'linha': n, 'nova': bool}}, caminho_do_arquivo).
    """
    try:
        from openpyxl import load_workbook
    except ImportError as exc:
        raise PlanilhaErro('Falta instalar o openpyxl para editar a planilha.') from exc
    arquivo = caminho()
    if not arquivo.exists():
        raise PlanilhaErro(f'Planilha não encontrada: {arquivo}')
    try:
        livro = load_workbook(arquivo)
    except Exception as exc:
        raise PlanilhaErro(f'Não consegui abrir a planilha ({exc.__class__.__name__}). Ela está aberta no Excel?') from exc
    aba = settings.LAI_PLANILHA_ABA
    if aba not in livro.sheetnames:
        raise PlanilhaErro(f'A planilha não tem a aba "{aba}". Abas encontradas: {", ".join(livro.sheetnames)}.')
    folha = livro[aba]

    ultima = PRIMEIRA_LINHA - 1
    existentes = {}
    for numero in range(PRIMEIRA_LINHA, min(folha.max_row, LIMITE_VARREDURA) + 1):
        valor = folha.cell(numero, 1).value
        if valor not in (None, ''):
            ultima = numero
            existentes.setdefault(so_digitos(valor), numero)

    resultado = {}
    novas = []
    ajustou = False
    for linha in linhas:
        chave = so_digitos(linha['nup'])
        if chave in existentes:
            numero = existentes[chave]
            resultado[linha['nup']] = {'linha': numero, 'nova': False}
            # Tema editado pelo usuário no módulo: atualiza só a coluna OBJETO da linha que já existe.
            tema = tema_para_texto(linha.get('tema'))
            if linha.get('tema_manual') and tema and folha.cell(numero, 3).value != tema:
                folha.cell(numero, 3).value = tema
                resultado[linha['nup']]['objeto_atualizado'] = True
                ajustou = True
        else:
            novas.append(linha)
    if not novas and not ajustou:
        return resultado, arquivo

    modelo = ultima if ultima >= PRIMEIRA_LINHA else PRIMEIRA_LINHA
    dias = int(getattr(settings, 'LAI_PLANILHA_DIAS_SECRETARIA', 4))
    for linha in novas:
        ultima += 1
        _copiar_estilo(folha, modelo, ultima)
        folha.cell(ultima, 1).value = linha['nup']
        folha.cell(ultima, 2).value = _data(linha.get('cadastro'))
        folha.cell(ultima, 3).value = tema_para_texto(linha.get('tema'))
        prazo = _data(linha.get('prazo'))
        folha.cell(ultima, 4).value = prazo
        folha.cell(ultima, 6).value = (prazo - timedelta(days=dias)) if prazo else None
        folha.cell(ultima, 9).value = STATUS_INICIAL
        for coluna in (5, 7, 8, 10):
            folha.cell(ultima, coluna).value = None
        resultado[linha['nup']] = {'linha': ultima, 'nova': True}
        existentes[so_digitos(linha['nup'])] = ultima

    if settings.LAI_PLANILHA_MODO == 'original':
        backup = arquivo.with_name(f'{arquivo.stem}.bak-{datetime.now():%Y%m%d-%H%M%S}{arquivo.suffix}')
        shutil.copy2(arquivo, backup)
    try:
        livro.save(arquivo)
    except PermissionError as exc:
        raise PlanilhaErro('Não consegui gravar a planilha. Feche-a no Excel e tente de novo.') from exc
    return resultado, arquivo


def _data(valor):
    if valor is None or valor == '':
        return None
    if isinstance(valor, datetime):
        return valor
    return datetime(valor.year, valor.month, valor.day)


def _copiar_estilo(folha, origem, destino):
    folha.row_dimensions[destino].height = folha.row_dimensions[origem].height
    for coluna in range(1, COLUNAS + 1):
        de = folha.cell(origem, coluna)
        para = folha.cell(destino, coluna)
        if de.has_style:
            para.font = copy(de.font)
            para.fill = copy(de.fill)
            para.border = copy(de.border)
            para.alignment = copy(de.alignment)
            para.number_format = de.number_format
