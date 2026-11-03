"""Nomes e sequência das pastas dos pedidos, no padrão do controle da CGM.

Cada pedido ganha uma pasta dentro da pasta do ano:

    77 - 03996.2026.000716-40 - DESPESAS COM RECEITAS VINCULADAS PETROLEO - LEI 12.858

- 77 é a sequência (continua do maior número que já existe na pasta do ano);
- depois vêm o NUP e o tema (por padrão, o assunto da lista do Fala.BR, em maiúsculas).
Dentro da pasta ficam o PDF `DetalhesNUP_<NUP sem pontos>.pdf` e os anexos, com o nome
`<NUP com pontos>_pdf_<n>.<ext>`.
"""
import logging
import re
from pathlib import Path

log = logging.getLogger(__name__)

LIMITE_TEMA = 90
_INVALIDOS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_SEQUENCIA = re.compile(r'^\s*(\d+)\s*-\s')


def so_digitos(texto):
    return re.sub(r'\D', '', str(texto or ''))


def tema_para_texto(tema):
    """Tema em maiúsculas e sem espaços repetidos. Vai para a coluna OBJETO da planilha."""
    return re.sub(r'\s+', ' ', str(tema or '')).strip().upper()


def tema_para_pasta(tema):
    """Mesmo tema, com os caracteres que o Windows não aceita em nome de pasta trocados por "_"."""
    texto = _INVALIDOS.sub('_', tema_para_texto(tema))
    texto = texto[:LIMITE_TEMA].strip(' .')
    return texto or 'SEM TEMA'


_SAUDACAO = re.compile(
    r'^\s*(?:(?:bom dia|boa tarde|boa noite|ol[aá]|prezad[oa]s?(?:\s+senhor(?:es|a|as)?)?|senhor(?:es|a|as)?|'
    r'sr\.?s?|sra\.?s?)\b[\s,.:;!\-]*)+', re.I)
_ABERTURA = re.compile(
    r'\b(?:com fundamento|com base|nos termos|em atendimento|em aten[cç][aã]o|venho|solicito|requeiro|'
    r'gostaria|conforme previsto|segundo o|amparad[oa])\b', re.I)
# Cabeçalho da plataforma, que às vezes vem colado no começo do texto do pedido.
_CABECALHO = re.compile(
    r'plataforma integrada de ouvidoria e acesso [àa] informa[cç][aã]o|detalhes da manifesta[cç][aã]o', re.I)
_ASSUNTO = re.compile(r'\bassunto\s*:\s*', re.I)
_ROTULO = re.compile(r'^\s*(?:assunto|resumo|teor)\s*:\s*', re.I)
_CPF = re.compile(r'\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b')
_EMAIL = re.compile(r'\S+@\S+')


def sugerir_tema(texto, limite=LIMITE_TEMA):
    """Sugestão de tema a partir do resumo/teor do pedido. O usuário revisa e pode trocar.

    Tira rótulo e saudação do começo, CPF e e-mail, e corta no fim de uma palavra.
    """
    bruto = _CABECALHO.sub(' ', str(texto or ''))
    # Se o texto tem "Assunto: título", o título (até a próxima linha em branco) é o tema,
    # esteja onde estiver. Isso é feito antes de juntar as linhas.
    com_assunto = _ASSUNTO.search(bruto)
    if com_assunto and bruto[com_assunto.end():].strip():
        bruto = re.split(r'\n\s*\n', bruto[com_assunto.end():].lstrip(), maxsplit=1)[0]
    t = re.sub(r'\s+', ' ', bruto).strip()
    t = _ROTULO.sub('', t)
    t = _SAUDACAO.sub('', t)
    t = _EMAIL.sub('', _CPF.sub('', t))
    # O pedido costuma ser "Assunto: título. Com fundamento na Lei...": o tema é só o título.
    corte = _ABERTURA.search(t)
    if corte and corte.start() >= 12:
        t = t[:corte.start()]
    t = re.sub(r'\s+', ' ', t).strip(' ,.;:-')
    if len(t) > limite:
        corte = t[:limite]
        t = corte.rsplit(' ', 1)[0] if ' ' in corte else corte
    return t.strip(' ,.;:-')


def nome_da_pasta(sequencia, nup, tema):
    return f'{int(sequencia)} - {nup} - {tema_para_pasta(tema)}'


def nome_do_pdf(nup):
    return f'DetalhesNUP_{so_digitos(nup)}.pdf'


def nome_do_anexo(nome, nup):
    """O Fala.BR entrega `03996202600071306_pdf_1.pdf`; a pasta usa o NUP com pontos."""
    digitos = so_digitos(nup)
    if digitos and str(nome).startswith(digitos):
        return str(nup) + str(nome)[len(digitos):]
    return str(nome)


def proxima_sequencia(base):
    """Maior número de sequência entre as pastas existentes, mais um."""
    maior = 0
    base = Path(base)
    if base.is_dir():
        for filho in base.iterdir():
            achado = _SEQUENCIA.match(filho.name) if filho.is_dir() else None
            if achado:
                maior = max(maior, int(achado.group(1)))
    return maior + 1


def achar_pasta(base, nup):
    """Pasta já criada para este NUP, ou None."""
    base = Path(base)
    if not base.is_dir():
        return None
    for filho in sorted(base.iterdir()):
        if filho.is_dir() and _SEQUENCIA.match(filho.name) and f' - {nup} - ' in f'{filho.name} ':
            return filho
    return None


def preparar_pasta(base, nup, tema, sequencia):
    """Devolve (pasta, criada, sequencia_usada).

    Se o NUP já tem pasta, reaproveita (e ajusta o tema no nome, se mudou). Senão cria com
    a `sequencia` recebida. Quem chama soma 1 à sequência só quando `criada` for verdadeiro.
    """
    base = Path(base)
    base.mkdir(parents=True, exist_ok=True)
    existente = achar_pasta(base, nup)
    if existente is not None:
        numero = int(_SEQUENCIA.match(existente.name).group(1))
        desejado = base / nome_da_pasta(numero, nup, tema)
        if desejado.name != existente.name and not desejado.exists():
            try:
                existente.rename(desejado)
                return desejado, False, numero
            except OSError:
                log.warning('Não foi possível renomear %s (pasta aberta?).', existente.name)
        return existente, False, numero
    pasta = base / nome_da_pasta(sequencia, nup, tema)
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta, True, sequencia
