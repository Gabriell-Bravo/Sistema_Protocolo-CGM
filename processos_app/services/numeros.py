# processos_app/services/numeros.py
"""Normalização de números de processo (com ou sem ponto milhar)."""


def normalizar_numero(valor):
    """18.245/2025 → 18245/2025; remove espaços."""
    texto = str(valor or '').strip()
    if not texto or texto.lower() in ('none', 'nan', '-'):
        return ''
    if isinstance(valor, float) and valor == int(valor):
        texto = str(int(valor))
    texto = texto.replace(' ', '')
    if '/' in texto:
        esquerda, direita = texto.split('/', 1)
        return f'{esquerda.replace(".", "")}/{direita.replace(".", "")}'
    return texto.replace('.', '')


def chaves_dupla_origem_pagamento(processo):
    """Conjunto {nº, origem/pagamento} normalizado; ordem dos campos irrelevante."""
    chaves = []
    for bruto in (
        getattr(processo, 'numero_processo', None),
        getattr(processo, 'processo_pagamento', None),
    ):
        chave = normalizar_numero(bruto)
        if chave and chave not in chaves:
            chaves.append(chave)
    return chaves