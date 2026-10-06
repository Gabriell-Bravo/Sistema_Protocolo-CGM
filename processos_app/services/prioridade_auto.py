# processos_app/services/prioridade_auto.py
"""Detecta prioridade na entrada por palavras-chave (listas da CGM)."""

import re
import unicodedata

from django.db import DatabaseError

# Ordem de precedência: urgente > obras > recorrente > normal.
PRECEDENCIA = ('URGENTE', 'PRIORITARIO', 'RECORRENTE', 'NORMAL')


def _normalizar(texto):
    bruto = unicodedata.normalize('NFKD', str(texto or ''))
    sem_acento = ''.join(c for c in bruto if not unicodedata.combining(c))
    return re.sub(r'\s+', ' ', sem_acento.casefold()).strip()


def _termos(bloco):
    termos = []
    for linha in str(bloco or '').splitlines():
        termo = _normalizar(linha)
        if termo:
            termos.append(termo)
    # Termos mais longos primeiro evitam "inova" engolir "consorcio inovar".
    termos.sort(key=len, reverse=True)
    return termos


def _contem(haystack, termo):
    if not haystack or not termo:
        return False
    # Termos curtos (siglas) exigem limite de palavra.
    if len(termo) <= 3:
        return re.search(
            rf'(^|[^a-z0-9]){re.escape(termo)}([^a-z0-9]|$)', haystack
        ) is not None
    return termo in haystack


def texto_do_processo(dados):
    """Campos da entrada usados na detecção."""
    partes = [
        dados.get('contratada'),
        dados.get('objeto'),
        dados.get('secretaria'),
        dados.get('numero_processo'),
    ]
    return _normalizar(' '.join(str(p or '') for p in partes))


def _mapa_palavras():
    """{codigo: [termos]} das prioridades ativas com palavras-chave."""
    try:
        from ..models import Prioridade
        linhas = Prioridade.objects.filter(ativo=True).values_list(
            'codigo', 'palavras_chave')
    except DatabaseError:
        return {}
    return {
        codigo: _termos(palavras)
        for codigo, palavras in linhas
        if (palavras or '').strip()
    }


def detectar_codigo(dados):
    """Devolve o código da prioridade detectada, ou None."""
    haystack = texto_do_processo(dados)
    if not haystack:
        return None
    mapa = _mapa_palavras()
    for codigo in PRECEDENCIA:
        for termo in mapa.get(codigo, ()):
            if _contem(haystack, termo):
                return codigo
    return None
