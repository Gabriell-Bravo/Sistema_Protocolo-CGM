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
    """[(termo_normalizado, texto_original), ...] — longos primeiro."""
    pares = []
    for linha in str(bloco or '').splitlines():
        original = linha.strip()
        termo = _normalizar(original)
        if termo:
            pares.append((termo, original))
    pares.sort(key=lambda item: len(item[0]), reverse=True)
    return pares


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
    """{codigo: [(termo, original), ...]} das prioridades ativas."""
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
    achado = sugerir(dados)
    return achado['codigo'] if achado else None


def sugerir(dados):
    """Devolve {codigo, nome, termo, prazo_dias} ou None."""
    haystack = texto_do_processo(dados)
    if not haystack:
        return None
    try:
        from ..models import Prioridade
        prioridades = {
            p.codigo: p
            for p in Prioridade.objects.filter(ativo=True)
        }
    except DatabaseError:
        prioridades = {}
    mapa = {
        codigo: _termos(getattr(prio, 'palavras_chave', ''))
        for codigo, prio in prioridades.items()
        if (getattr(prio, 'palavras_chave', None) or '').strip()
    }
    for codigo in PRECEDENCIA:
        for termo, original in mapa.get(codigo, ()):
            if not _contem(haystack, termo):
                continue
            prio = prioridades.get(codigo)
            return {
                'codigo': codigo,
                'nome': prio.nome if prio else codigo,
                'termo': original,
                'prazo_dias': prio.prazo_dias if prio else None,
            }
    return None
