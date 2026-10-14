"""Separa o texto corrido de uma diligência em itens de checklist.

Os analistas às vezes registram várias providências no mesmo campo
("1- Anexar...; 2- Regularizar..."). O ponto e vírgula sozinho não
separa item: ele também lista folhas ("fls. 30 a 38; 68, 75 a 84").
"""

import re

# 1)  1-  1.  a)  no começo, depois de espaço, ; . ou quebra.
# O traço só vale se o que vem depois é texto, não outra folha (15-27).
_MARCADOR = re.compile(
    r'(?:'
    r'(?:^|(?<=[\s;.\n]))(?:'
    r'\d{1,2}\s*\)\s*'
    r'|\d{1,2}\s*[-–—]\s*(?=[A-Za-zÀ-ÿ])'
    r'|\d{1,2}\.\s+(?=[A-Za-zÀ-ÿ])'
    r'|[A-Za-z]\)\s*'
    r')'
    r'|(?:^|\n)\s*[-•]\s+'
    r')',
    re.MULTILINE,
)

_VERBO = re.compile(
    r'^(?:regularizar|anexar|juntar|encaminhar|solicitar|apresentar|'
    r'corrigir|retificar|comprovar|esclarecer|providenciar|incluir|'
    r'acostar|autuar|informar|substituir|completar|sanar|obter|emitir|'
    r'assinar|inserir|atualizar|conferir|digitalizar|acolher|promover|'
    r'recomendar|orientar)\b',
    re.IGNORECASE,
)

_FOLHA_SOLTA = re.compile(r'^[A-Za-z]\s+\d')


def itens_para_checklist(texto, concluidos=None):
    """Cada providência, com a marca de já atendida quando a Gestão indicou."""
    feitos = set(concluidos or [])
    return [
        {'texto': item, 'concluido': item in feitos}
        for item in separar_itens(texto)
    ]


def separar_itens(texto):
    """Devolve cada providência identificada no texto, na ordem escrita."""
    bruto = _normalizar(texto)
    if not bruto:
        return []

    marcadores = [m for m in _MARCADOR.finditer(bruto) if _marcador_vale(bruto, m)]
    if len(marcadores) >= 1 and (
            len(marcadores) >= 2 or marcadores[0].start() == 0):
        partes = _fatiar_marcadores(bruto, marcadores)
    else:
        partes = _fatiar_linhas(bruto)

    itens = []
    for parte in partes:
        itens.extend(_fatiar_ponto_virgula(parte))

    limpos = []
    for item in itens:
        item = re.sub(r'\s+', ' ', item).strip(' ;')
        if item:
            limpos.append(item)
    if limpos:
        return limpos
    return [re.sub(r'\s+', ' ', bruto).strip()]


def _marcador_vale(texto, marcador):
    """'fl. 21. Regularizar' é folha, não o item 21 de uma lista."""
    trecho = marcador.group()
    if not re.match(r'\d{1,2}\.\s+', trecho):
        return True
    antes = texto[max(0, marcador.start() - 8):marcador.start()].lower()
    return re.search(r'(?:fls|fl|fs|f)\.\s*$', antes) is None


def _normalizar(texto):
    texto = (texto or '').replace('\r\n', '\n').replace('\r', '\n')
    return texto.replace('\u00a0', ' ').replace('\t', ' ').strip()


def _fatiar_marcadores(texto, marcadores):
    partes = []
    if marcadores[0].start() > 0:
        prefixo = texto[:marcadores[0].start()].strip()
        if prefixo:
            partes.append(prefixo)
    for indice, marcador in enumerate(marcadores):
        inicio = marcador.end()
        fim = (marcadores[indice + 1].start()
               if indice + 1 < len(marcadores) else len(texto))
        partes.append(texto[inicio:fim])
    return partes


def _fatiar_linhas(texto):
    blocos = []
    atual = ''
    for linha in texto.split('\n'):
        linha = linha.strip()
        if not linha:
            if atual:
                blocos.append(atual)
                atual = ''
            continue
        bullet = re.match(r'^[-•]\s+', linha)
        if bullet:
            if atual:
                blocos.append(atual)
                atual = ''
            blocos.append(linha[bullet.end():])
            continue
        if not atual or not _e_continuacao(linha):
            if atual:
                blocos.append(atual)
            atual = linha
        else:
            atual = f'{atual} {linha}'
    if atual:
        blocos.append(atual)
    return blocos


def _e_continuacao(linha):
    """Linha que segue a providência de cima (folha ou frase no meio)."""
    if not linha:
        return False
    if linha[0].isdigit():
        return True
    if linha[0].islower() and not _VERBO.match(linha):
        return True
    return False


def _fatiar_ponto_virgula(texto):
    pedacos = re.split(r';\s+', texto.strip())
    if len(pedacos) <= 1:
        return [texto] if texto.strip() else []
    itens = [pedacos[0]]
    for pedaco in pedacos[1:]:
        if _e_novo_item(pedaco):
            itens.append(pedaco)
        else:
            itens[-1] = f'{itens[-1]}; {pedaco}'
    return itens


def _e_novo_item(pedaco):
    pedaco = pedaco.strip()
    if not pedaco or pedaco[0].isdigit():
        return False
    if _FOLHA_SOLTA.match(pedaco):
        return False
    if _VERBO.match(pedaco):
        return True
    return pedaco[0].isupper() and len(pedaco) >= 12
