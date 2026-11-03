"""Acompanhamento das manifestações lidas do Fala.BR.

A leitura traz o que a lista do Fala.BR mostra (número, assunto, tipo,
cadastro, prazo e situação). Aqui isso é guardado, comparado com a leitura
anterior e cruzado com as demandas já cadastradas no módulo.
"""
import re
import unicodedata
from datetime import date, datetime

from django.db import transaction
from django.utils import timezone

from .models import ManifestacaoFalabr


def data_do_texto(valor):
    """Aceita date, 'dd/mm/aaaa', 'aaaa-mm-dd' e 'aaaa-mm-ddThh:mm:ss'."""
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    texto = str(valor or '').strip()
    if not texto:
        return None
    for formato, tamanho in (('%d/%m/%Y', 10), ('%Y-%m-%d', 10)):
        try:
            return datetime.strptime(texto[:tamanho], formato).date()
        except ValueError:
            continue
    return None


def _limpo(valor, limite):
    return re.sub(r'\s+', ' ', str(valor or '')).strip()[:limite]


def sincronizar_leitura(leitura):
    """Grava a leitura completa do Fala.BR (abertas e encerradas).

    Devolve {'total', 'novas', 'alteradas', 'abertas', 'encerradas', 'saiu', 'incompleta'}.
    Quem estava na fila aberta e não aparece mais na leitura fica como
    "Saiu da fila aberta", e só se a leitura das abertas veio completa.
    """
    grupos = leitura.get('grupos') or {}
    abertas = grupos.get('abertas') or {'linhas': [], 'completa': True}
    encerradas = grupos.get('encerradas') or {'linhas': [], 'completa': True}
    resultado = {'total': 0, 'novas': 0, 'alteradas': 0, 'abertas': 0, 'encerradas': 0, 'saiu': 0,
                 'incompleta': not (abertas.get('completa', True) and encerradas.get('completa', True))}
    # Abertas primeiro: se um número aparecer nas duas consultas, vale a encerrada, que é mais nova.
    for linhas, fila, chave in ((abertas['linhas'], 'ABERTA', 'abertas'),
                                (encerradas['linhas'], 'ENCERRADA', 'encerradas')):
        gravado = sincronizar(linhas, fila=fila)
        resultado[chave] = gravado['total']
        for campo in ('total', 'novas', 'alteradas'):
            resultado[campo] += gravado[campo]
    if abertas['linhas'] and abertas.get('completa', True):
        lidos = {re.sub(r'\D', '', str(l.get('nup') or '')) for l in abertas['linhas'] + encerradas['linhas']}
        sumiram = ManifestacaoFalabr.objects.filter(fila='ABERTA').exclude(nup_normalizada__in=lidos)
        resultado['saiu'] = sumiram.update(fila='SAIU')
    return resultado


def sincronizar(linhas, fila='ABERTA'):
    """Grava as linhas lidas. Devolve {'total', 'novas', 'alteradas'}.

    Campo vazio na leitura nova não apaga o que já estava guardado.
    Mudança de prazo ou de situação guarda o valor anterior e a data.
    """
    agora = timezone.now()
    novas = alteradas = total = 0
    with transaction.atomic():
        for linha in linhas:
            chave = re.sub(r'\D', '', str(linha.get('nup') or ''))
            if len(chave) != 17:
                continue
            total += 1
            prazo = data_do_texto(linha.get('prazo'))
            cadastro = data_do_texto(linha.get('cadastro'))
            situacao = _limpo(linha.get('situacao'), 80)
            campos = dict(
                nup=_limpo(linha.get('nup'), 40),
                orgao=_limpo(linha.get('orgao'), 180),
                assunto=_limpo(linha.get('assunto'), 400),
                servico=_limpo(linha.get('servico'), 240),
                tipo=_limpo(linha.get('tipo'), 180),
                responsavel=_limpo(linha.get('responsavel'), 180),
                link=_limpo(linha.get('link'), 300),
            )
            obj = ManifestacaoFalabr.objects.filter(nup_normalizada=chave).first()
            if obj is None:
                ManifestacaoFalabr.objects.create(
                    cadastro=cadastro, prazo=prazo, situacao=situacao, fila=fila,
                    ultima_leitura=agora, **campos)
                novas += 1
                continue
            mudou = False
            if prazo and obj.prazo and prazo != obj.prazo:
                obj.prazo_anterior = obj.prazo
                mudou = True
            if situacao and obj.situacao and situacao != obj.situacao:
                obj.situacao_anterior = obj.situacao
                mudou = True
            if mudou:
                obj.alterado_em = agora
                alteradas += 1
            for nome, valor in campos.items():
                if valor:
                    setattr(obj, nome, valor)
            if prazo:
                obj.prazo = prazo
            if cadastro:
                obj.cadastro = cadastro
            if situacao:
                obj.situacao = situacao
            obj.fila = fila
            obj.ultima_leitura = agora
            obj.save()
    return {'total': total, 'novas': novas, 'alteradas': alteradas}


def _classe_prazo(dias):
    if dias is None:
        return ''
    if dias <= 2:
        return 'vermelho'
    if dias <= 5:
        return 'laranja'
    if dias <= 10:
        return 'amarelo'
    return ''


def _texto_dias(dias):
    if dias is None:
        return 'Prazo não informado'
    if dias < 0:
        return f'Vencido há {-dias} dia(s)'
    if dias == 0:
        return 'Vence hoje'
    if dias == 1:
        return 'Vence amanhã'
    return f'{dias} dias restantes'


def _alteracao(prazo_anterior, prazo, situacao_anterior, situacao):
    partes = []
    if prazo_anterior and prazo and prazo_anterior != prazo:
        partes.append(f'Prazo mudou de {prazo_anterior:%d/%m/%Y} para {prazo:%d/%m/%Y}')
    if situacao_anterior and situacao and situacao_anterior != situacao:
        partes.append(f'Situação mudou de {situacao_anterior} para {situacao}')
    return '. '.join(partes)


def montar_lista(registros, demandas, hoje=None):
    """Junta leitura e demandas cadastradas. Cada item é um dicionário para a tela.

    `registros` pode ser ManifestacaoFalabr ou dicionários vindos da API.
    """
    hoje = hoje or timezone.localdate()
    cadastradas = {d.nup_normalizada: d for d in demandas}
    itens = []
    for r in registros:
        if isinstance(r, ManifestacaoFalabr):
            base = dict(
                pk=r.pk, nup=r.nup, nup_normalizada=r.nup_normalizada,
                assunto=r.assunto, tipo=r.tipo, situacao=r.situacao,
                cadastro=r.cadastro, prazo=r.prazo, responsavel=r.responsavel,
                link=r.link, lida_em=r.ultima_leitura, fila=r.fila,
                tema=r.tema, tema_efetivo=r.tema_efetivo, pasta=r.pasta, baixado_em=r.baixado_em,
                alteracao=_alteracao(r.prazo_anterior, r.prazo, r.situacao_anterior, r.situacao),
                alterado_em=r.alterado_em)
        else:
            base = dict(
                pk=None, nup=r.get('nup', ''), nup_normalizada=r.get('nup_normalizada', ''),
                assunto=r.get('assunto', ''), tipo=r.get('tipo', ''), situacao=r.get('situacao', ''),
                cadastro=data_do_texto(r.get('cadastro')), prazo=data_do_texto(r.get('prazo')),
                responsavel=r.get('responsavel', ''), link=r.get('link', ''),
                lida_em=None, fila=r.get('fila', 'ABERTA'), alteracao='', alterado_em=None,
                tema='', tema_efetivo=r.get('assunto', ''), pasta='', baixado_em=None)
        aberta = base['fila'] == 'ABERTA'
        dias = (base['prazo'] - hoje).days if base['prazo'] else None
        base['dias'] = dias
        base['dias_texto'] = _texto_dias(dias) if aberta else ('Encerrada' if base['fila'] == 'ENCERRADA' else 'Saiu da fila aberta')
        base['classe'] = _classe_prazo(dias) if aberta else ''
        demanda = cadastradas.get(base['nup_normalizada'])
        base['demanda'] = demanda
        base['prazo_modulo'] = None
        if demanda is not None and base['prazo'] and demanda.vencimento != base['prazo']:
            base['prazo_modulo'] = demanda.vencimento
        base['faixa'] = _faixa(base, aberta, dias)
        base['prorrogada'] = aberta and 'prorrog' in _chave(base['situacao'])
        base['avisos'] = _avisos(base, demanda, aberta)
        itens.append(base)
    itens.sort(key=lambda i: (i['prazo'] is None, i['prazo'] or hoje, i['nup']))
    return itens


def _chave(texto):
    sem_acento = ''.join(c for c in unicodedata.normalize('NFD', texto or '') if unicodedata.category(c) != 'Mn')
    return re.sub(r'[^a-z]', '', sem_acento.lower())


def _faixa(item, aberta, dias):
    """Em que faixa de acompanhamento a manifestação está."""
    if not aberta:
        return 'encerrada' if item['fila'] == 'ENCERRADA' else 'saiu'
    chave = _chave(item['situacao'])
    if 'complementacao' in chave and 'solicit' in chave:
        return 'aguardando'
    if dias is None:
        return 'sem_prazo'
    if dias < 0:
        return 'vencida'
    if dias == 0:
        return 'hoje'
    if dias <= 5:
        return 'urgente'
    return 'no_prazo'


def _avisos(item, demanda, aberta):
    """Divergências entre o Fala.BR e o módulo, que a equipe precisa resolver."""
    avisos = []
    if demanda is not None:
        if aberta and demanda.status == 'RESPOSTA_INTERNA':
            avisos.append('Falta registrar a resposta no Fala.BR.')
        elif aberta and demanda.encerrada:
            avisos.append('Marcada como respondida ou arquivada no módulo, mas ainda aberta no Fala.BR.')
        elif item['fila'] == 'ENCERRADA' and not demanda.encerrada:
            avisos.append('Encerrada no Fala.BR, mas ainda aberta no módulo.')
        if item['prazo_modulo']:
            avisos.append(f'Prazo no módulo ({item["prazo_modulo"]:%d/%m/%Y}) é diferente do Fala.BR.')
    return avisos


FILTROS = [
    # (chave, rótulo, função que diz se o item entra)
    ('abertas', 'Abertas', lambda i: i['fila'] == 'ABERTA'),
    ('vencidas', 'Vencidas', lambda i: i['faixa'] == 'vencida'),
    ('hoje', 'Vencem hoje', lambda i: i['faixa'] == 'hoje'),
    ('urgentes', 'Vencem em até 5 dias', lambda i: i['faixa'] == 'urgente'),
    ('no_prazo', 'No prazo', lambda i: i['faixa'] == 'no_prazo'),
    ('aguardando', 'Aguardando o cidadão', lambda i: i['faixa'] == 'aguardando'),
    ('prorrogadas', 'Prorrogadas', lambda i: i['prorrogada']),
    ('sem_modulo', 'Sem cadastro no módulo', lambda i: i['fila'] == 'ABERTA' and i['demanda'] is None),
    ('divergencias', 'Divergências', lambda i: bool(i['avisos'])),
    ('alteradas', 'Com mudança', lambda i: bool(i['alteracao'])),
    ('encerradas', 'Encerradas', lambda i: i['fila'] == 'ENCERRADA'),
    ('saiu', 'Saíram da fila', lambda i: i['fila'] == 'SAIU'),
    ('todas', 'Todas', lambda i: True),
]
_FILTROS = {chave: funcao for chave, _rotulo, funcao in FILTROS}
# Severidade só para a cor dos cartões.
_CLASSE_CARTAO = {'vencidas': 'vermelho', 'hoje': 'vermelho', 'urgentes': 'laranja', 'divergencias': 'amarelo'}


def filtrar(itens, filtro='abertas', busca=''):
    """Aplica o filtro por faixa e a busca por NUP, assunto, responsável ou situação."""
    funcao = _FILTROS.get(filtro) or _FILTROS['abertas']
    selecionados = [i for i in itens if funcao(i)]
    termo = _chave(busca)
    digitos = re.sub(r'\D', '', busca or '')
    if termo or digitos:
        def combina(i):
            if digitos and digitos in i['nup_normalizada']:
                return True
            alvo = _chave(' '.join([i['assunto'], i['responsavel'], i['situacao'], i['tipo']]))
            return bool(termo) and termo in alvo
        selecionados = [i for i in selecionados if combina(i)]
    if filtro in ('encerradas', 'saiu'):
        selecionados.sort(key=lambda i: (i['cadastro'] or date.min, i['nup']), reverse=True)
    return selecionados


def filtro_valido(filtro):
    return filtro if filtro in _FILTROS else 'abertas'


def resumo(itens):
    """Cartões do painel. Cada um aponta para o filtro correspondente."""
    cartoes = []
    for chave, rotulo, funcao in FILTROS:
        if chave in ('todas', 'alteradas', 'saiu'):
            continue
        cartoes.append({
            'filtro': chave, 'rotulo': rotulo,
            'valor': sum(1 for i in itens if funcao(i)),
            'classe': _CLASSE_CARTAO.get(chave, ''),
        })
    return cartoes


def dados_iniciais(manifestacao):
    """Valores do formulário de cadastro a partir da leitura do Fala.BR."""
    return {
        'nup': manifestacao.nup,
        'tipo': manifestacao.tipo,
        'cadastro_falabr': manifestacao.cadastro,
        'marco_inicial': manifestacao.cadastro,
        'vencimento_original': manifestacao.prazo,
        'prazo_interno': manifestacao.prazo,
        'resumo': manifestacao.assunto,
    }
