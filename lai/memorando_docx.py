"""Memorando de reiteração da LAI em .docx, a partir do modelo da Controladoria.

O modelo (`modelos/memorando_reitera.docx`) é o memorando original com os trechos que mudam
trocados por campos `{{NOME}}`. Aqui só se troca o texto desses campos: cabeçalho, brasão,
assinatura e formatação ficam exatamente como no modelo. Nenhuma biblioteca extra é usada.
"""
import io
import re
import zipfile
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

MODELO = Path(__file__).resolve().parent / 'modelos' / 'memorando_reitera.docx'

MESES = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro',
         'outubro', 'novembro', 'dezembro']

TRATAMENTOS = {
    'secretario': 'Senhor Secretário,',
    'secretaria': 'Senhora Secretária,',
}

OBSERVACOES = {
    'nenhuma': '.',
    'vencido': ', considerando prazo vencido.',
    'prorrogado': ', considerando prazo já prorrogado.',
    'ambos': ', considerando prazo vencido e já prorrogado.',
}

CAMPOS = ('DATA_DIA_MES', 'DATA_ANO', 'NUMERO', 'SECRETARIA', 'NUP', 'TRATAMENTO',
          'PRAZO_DIA_MES', 'PRAZO_ANO', 'PRAZO_OBS')


class MemorandoError(ValueError):
    """Dado inválido para montar o memorando (a mensagem pode ser mostrada à pessoa)."""


def dia_e_mes(data):
    return f'{data.day} de {MESES[data.month - 1]}'


def observacao_padrao(prazo, hoje, prorrogada):
    vencido = bool(prazo and prazo < hoje)
    if vencido and prorrogada:
        return 'ambos'
    if vencido:
        return 'vencido'
    if prorrogada:
        return 'prorrogado'
    return 'nenhuma'


def numero_formatado(numero, ano):
    return f'{int(numero)}/{int(ano)}/LAI/CGM'


def nome_do_arquivo(numero, ano, nup):
    nup = re.sub(r'[^0-9.\-]', '', nup or '')
    return f'MEMO {int(numero)}-{int(ano)}-CGM - REITERA LAI NUP {nup}.docx'


def _texto(valor, rotulo, maximo):
    valor = ' '.join(str(valor or '').split())
    if not valor:
        raise MemorandoError(f'Informe {rotulo}.')
    if len(valor) > maximo:
        raise MemorandoError(f'{rotulo[0].upper() + rotulo[1:]} passa de {maximo} caracteres.')
    return valor


def gerar(*, numero, data, nup, secretaria, prazo, tratamento='secretario', observacao='nenhuma'):
    """Devolve os bytes do .docx. `data` e `prazo` são `datetime.date`."""
    if not isinstance(data, date) or not isinstance(prazo, date):
        raise MemorandoError('Data do memorando e prazo da resposta precisam ser datas válidas.')
    try:
        numero = int(numero)
    except (TypeError, ValueError):
        raise MemorandoError('O número do memorando precisa ser um número inteiro.')
    if not 1 <= numero <= 99999:
        raise MemorandoError('O número do memorando precisa estar entre 1 e 99999.')
    if tratamento not in TRATAMENTOS:
        raise MemorandoError('Tratamento inválido.')
    if observacao not in OBSERVACOES:
        raise MemorandoError('Observação do prazo inválida.')
    valores = {
        'DATA_DIA_MES': dia_e_mes(data),
        'DATA_ANO': str(data.year),
        'NUMERO': numero_formatado(numero, data.year),
        'SECRETARIA': _texto(secretaria, 'a secretaria de destino', 160),
        'NUP': _texto(nup, 'o NUP', 40),
        'TRATAMENTO': TRATAMENTOS[tratamento],
        'PRAZO_DIA_MES': dia_e_mes(prazo),
        'PRAZO_ANO': str(prazo.year),
        'PRAZO_OBS': OBSERVACOES[observacao],
    }
    with zipfile.ZipFile(MODELO) as entrada:
        saida_bytes = io.BytesIO()
        with zipfile.ZipFile(saida_bytes, 'w', zipfile.ZIP_DEFLATED) as saida:
            for info in entrada.infolist():
                dados = entrada.read(info.filename)
                if info.filename == 'word/document.xml':
                    dados = _preencher(dados.decode('utf-8'), valores).encode('utf-8')
                saida.writestr(info.filename, dados)
    return saida_bytes.getvalue()


def _preencher(xml, valores):
    def troca(achado):
        nome = achado.group(1)
        if nome not in valores:
            raise MemorandoError(f'O modelo tem um campo desconhecido: {nome}.')
        return escape(valores[nome])
    xml = re.sub(r'\{\{([A-Z_]+)\}\}', troca, xml)
    if '{{' in xml:
        raise MemorandoError('O modelo ficou com campos sem preencher.')
    return xml
