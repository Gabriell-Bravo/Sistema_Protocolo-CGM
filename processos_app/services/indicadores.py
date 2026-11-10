# processos_app/services/indicadores.py
"""
Dashboard da Gestão, quadro da equipe, indicadores do período e tempos do
fluxo (itens 47 a 50).

Tudo aqui é CÁLCULO sobre o que o sistema já registra (item 1): nenhum
número é digitado. Contagens e estoques saem dos estados; tempos saem dos
carimbos de data/hora gravados pela tramitação.

Sem ranking de servidores (item 48): o quadro da equipe mostra carga de
trabalho em ordem alfabética, nunca ordenado por desempenho.
"""

from datetime import datetime, timedelta

from django.db.models import Count, Exists, OuterRef, Q
from django.urls import reverse
from django.utils import timezone

from ..models import Pendencia, Processo
from . import gestao_pessoas, prazos, tramitacao
from . import permissions as perm


def _url(nome, consulta=''):
    return reverse(nome) + (f'?{consulta}' if consulta else '')


# --------------------------------------------------------------------------
# Cards (item 47) — todos clicáveis
# --------------------------------------------------------------------------

def _com_percentual(linhas):
    """Largura da barra em relação ao maior valor do próprio gráfico."""
    maior = max((item['valor'] or 0 for item in linhas), default=0)
    for item in linhas:
        valor = item['valor'] or 0
        item['pct'] = 0 if not valor or not maior else max(6, round(100 * valor / maior))
    return linhas


def panorama(referencia=None):
    """Recorte de agora: onde o processo está, a prioridade e o prazo."""
    hoje = referencia or timezone.localdate()
    ativos = list(tramitacao.ativos().only(
        'id', 'situacao_tramite', 'prioridade', 'data_entrada'))

    por_situacao = {}
    por_prioridade = {'NORMAL': 0, 'PRIORITARIO': 0, 'URGENTE': 0}
    no_prazo = vence_hoje = vencido = 0
    for processo in ativos:
        por_situacao[processo.situacao_tramite] = por_situacao.get(processo.situacao_tramite, 0) + 1
        codigo = processo.prioridade if processo.prioridade in por_prioridade else 'NORMAL'
        por_prioridade[codigo] += 1
        dias = prazos.dias_restantes(processo, hoje)
        if dias is None:
            continue
        if dias < 0:
            vencido += 1
        elif dias == 0:
            vence_hoje += 1
        else:
            no_prazo += 1

    rotulos = dict(Processo.SITUACAO_TRAMITE_CHOICES)
    return {
        'situacao': _com_percentual([
            {'rotulo': rotulos['DISPONIVEL'], 'valor': por_situacao.get('DISPONIVEL', 0), 'cor': 'ok'},
            {'rotulo': rotulos['EM_ANALISE'], 'valor': por_situacao.get('EM_ANALISE', 0), 'cor': 'info'},
            {'rotulo': rotulos['ASSINATURA_DIRECIONADA'], 'valor': por_situacao.get('ASSINATURA_DIRECIONADA', 0), 'cor': 'info'},
            # Disponível para retirada já passou pelo Controlador: conta junto.
            {'rotulo': rotulos['AGUARDANDO_ASSINATURA'],
             'valor': por_situacao.get('AGUARDANDO_ASSINATURA', 0) + por_situacao.get('DISPONIVEL_RETIRADA', 0),
             'cor': 'alerta'},
        ]),
        'prioridade': _com_percentual([
            {'rotulo': 'Normal', 'valor': por_prioridade['NORMAL'], 'cor': 'ok'},
            {'rotulo': 'Prioritário', 'valor': por_prioridade['PRIORITARIO'], 'cor': 'alerta'},
            {'rotulo': 'Urgente', 'valor': por_prioridade['URGENTE'], 'cor': 'perigo'},
        ]),
        'prazo': _com_percentual([
            {'rotulo': 'No prazo', 'valor': no_prazo, 'cor': 'ok'},
            {'rotulo': 'Vence hoje', 'valor': vence_hoje, 'cor': 'alerta'},
            {'rotulo': 'Vencido', 'valor': vencido, 'cor': 'perigo'},
        ]),
    }


def cards(referencia=None):
    ativos = tramitacao.ativos()

    por_situacao = dict(ativos.values_list('situacao_tramite')
                        .annotate(total=Count('id')).values_list('situacao_tramite', 'total'))
    # "Disponível para retirada" não tem card próprio: o processo já foi
    # analisado e assinado, então conta em "Com o Controlador". Assim os
    # cards sempre somam o total em tramitação.
    com_controlador = (por_situacao.get('AGUARDANDO_ASSINATURA', 0)
                       + por_situacao.get('DISPONIVEL_RETIRADA', 0))

    return [
        {'rotulo': 'Em tramitação', 'valor': sum(por_situacao.values()),
         'icone': 'account_tree', 'cor': 'primary', 'url': _url('listar_processos')},
        {'rotulo': 'Disponíveis para análise', 'valor': por_situacao.get('DISPONIVEL', 0),
         'icone': 'front_hand', 'cor': 'success', 'url': _url('gestao_processos', 'filtro=disponiveis')},
        {'rotulo': 'Em análise', 'valor': por_situacao.get('EM_ANALISE', 0)
                                          + por_situacao.get('ASSINATURA_DIRECIONADA', 0),
         'icone': 'manage_accounts', 'cor': 'violet', 'url': _url('gestao_processos', 'filtro=em_analise')},
        {'rotulo': 'Com o Controlador', 'valor': com_controlador,
         'icone': 'draw', 'cor': 'primary',
         'url': _url('gestao_processos', 'filtro=liberados')},
        {'rotulo': 'Urgentes', 'valor': ativos.filter(prioridade='URGENTE').count(),
         'icone': 'priority_high', 'cor': 'danger', 'url': _url('gestao_processos', 'filtro=urgentes')},
        {'rotulo': 'Diligências', 'icone': 'campaign', 'cor': 'warning',
         'valor': Pendencia.objects.filter(status='AGUARDANDO_ATENDIMENTO').count(),
         'url': _url('gestao_diligencias')},
    ]


# --------------------------------------------------------------------------
# Quadro da equipe (item 48)
# --------------------------------------------------------------------------

def equipe(inicio, fim, referencia=None):
    """Analistas ativos com disponibilidade (Gestão de Pessoas CGM), carga
    atual, vencidos e concluídos no período. Ordem alfabética."""
    hoje = referencia or timezone.localdate()
    analistas = list(perm.analistas_ativos())
    disponibilidade = gestao_pessoas.mapa_disponibilidade(analistas, hoje)
    ativos = tramitacao.ativos()

    linhas = []
    for analista in analistas:
        em_analise = list(ativos.filter(
            analista_responsavel=analista,
            situacao_tramite__in=['EM_ANALISE', 'ASSINATURA_DIRECIONADA'])
            .select_related(None)
            .only('id', 'data_entrada', 'prioridade'))
        vencidos = sum(1 for p in em_analise
                       if (prazos.dias_restantes(p, hoje) or 0) < 0)
        concluidos = Processo.objects.filter(
            analista_responsavel=analista,
            liberado_assinatura_em__date__gte=inicio,
            liberado_assinatura_em__date__lte=fim).count()
        linhas.append({
            'nome': perm.nome_usuario(analista),
            'grupo': ' / '.join(
                Processo.GENERO_LABELS.get(g, g)
                for g in sorted(perm.grupos_do_analista(analista))
            ) or '—',
            'disponibilidade': disponibilidade.get(analista.id, gestao_pessoas.DISPONIVEL),
            'disponivel': disponibilidade.get(analista.id) == gestao_pessoas.DISPONIVEL,
            'em_analise': len(em_analise),
            'vencidos': vencidos,
            'concluidos': concluidos,
        })
    return linhas


# --------------------------------------------------------------------------
# Indicadores do período (item 49)
# --------------------------------------------------------------------------

def aplicar_filtros(consulta, grupo=None, analista=None, secretaria=None, especie=None):
    if grupo:
        consulta = consulta.filter(genero=grupo)
    if analista:
        consulta = consulta.filter(analista_responsavel_id=analista)
    if secretaria:
        consulta = consulta.filter(secretaria__icontains=secretaria)
    if especie:
        consulta = consulta.filter(especie_fk_id=especie)
    return consulta


def _saiu_ate(corte):
    """Q de 'já tinha saído até a data de corte' (fluxo novo ou legado)."""
    return Q(saida_concluida_em__date__lte=corte) | Q(
        saida_concluida_em__isnull=True, data_saida__lte=corte)


def periodo(inicio, fim, **filtros):
    base = aplicar_filtros(Processo.objects.filter(cancelado_em__isnull=True), **filtros)

    recebidos = base.filter(data_entrada__gte=inicio, data_entrada__lte=fim)
    liberados = base.filter(liberado_assinatura_em__date__gte=inicio,
                            liberado_assinatura_em__date__lte=fim)
    saidas = base.filter(
        Q(saida_concluida_em__date__gte=inicio, saida_concluida_em__date__lte=fim)
        | Q(saida_concluida_em__isnull=True, data_saida__gte=inicio, data_saida__lte=fim))

    def estoque(corte):
        return base.filter(data_entrada__lte=corte).exclude(_saiu_ate(corte)).count()

    # Retorno/reanálise: entrada no período de um número que já tinha
    # passado pela CGM antes.
    anterior = Processo.objects.filter(
        numero_processo=OuterRef('numero_processo'),
        data_entrada__lt=OuterRef('data_entrada'))
    retornos = recebidos.annotate(ja_passou=Exists(anterior)).filter(ja_passou=True).count()

    rotulos = dict(Processo.GENERO_LABELS)
    por_grupo = _com_percentual([
        {'rotulo': rotulos.get(l['genero'], l['genero'] or '—'),
         'valor': l['total'], 'cor': 'info'}
        for l in recebidos.values('genero').annotate(total=Count('id')).order_by('-total')
    ])
    por_secretaria = _com_percentual([
        {'rotulo': l['secretaria'] or '—', 'valor': l['total'], 'cor': 'info'}
        for l in recebidos.values('secretaria').annotate(total=Count('id')).order_by('-total', 'secretaria')
    ])
    por_especie = _com_percentual([
        {'rotulo': l['especie'] or '—', 'valor': l['total'], 'cor': 'neutro'}
        for l in recebidos.values('especie').annotate(total=Count('id')).order_by('-total', 'especie')
    ])
    return {
        'recebidos': recebidos.count(),
        'liberados_assinatura': liberados.count(),
        'saidas_concluidas': saidas.count(),
        'estoque_inicial': estoque(inicio - timedelta(days=1)),
        'estoque_final': estoque(fim),
        'retornos': retornos,
        'por_grupo': por_grupo,
        'por_secretaria': por_secretaria,
        'por_especie': por_especie,
        'movimento': _com_percentual([
            {'rotulo': 'Recebidos', 'valor': recebidos.count(), 'cor': 'info'},
            {'rotulo': 'Liberados para assinatura', 'valor': liberados.count(), 'cor': 'alerta'},
            {'rotulo': 'Saídas concluídas', 'valor': saidas.count(), 'cor': 'ok'},
            {'rotulo': 'Retornos', 'valor': retornos, 'cor': 'neutro'},
        ]),
    }


# --------------------------------------------------------------------------
# Fluxo: quantos entraram e quantos saíram (gráfico principal)
# --------------------------------------------------------------------------

UNIDADES_FLUXO = (
    ('dia', 'Dia'), ('semana', 'Semana'), ('mes', 'Mês'), ('ano', 'Ano'),
)
_ORDEM_UNIDADES = [codigo for codigo, _ in UNIDADES_FLUXO]
_MAX_BALDES = 62
_MESES_CURTOS = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun',
                 'jul', 'ago', 'set', 'out', 'nov', 'dez']


def _meses_atras(data, meses):
    total = data.year * 12 + (data.month - 1) - meses
    return data.replace(year=total // 12, month=total % 12 + 1, day=1)


def janela_padrao(unidade, hoje):
    """Período mostrado quando o usuário só escolhe Dia/Semana/Mês/Ano."""
    if unidade == 'semana':
        segunda = hoje - timedelta(days=hoje.weekday())
        return segunda - timedelta(weeks=11), hoje
    if unidade == 'mes':
        return _meses_atras(hoje.replace(day=1), 11), hoje
    if unidade == 'ano':
        return hoje.replace(year=hoje.year - 4, month=1, day=1), hoje
    return hoje, hoje  # Dia = um dia só (hoje); o gráfico mostra os 7 dias até ele.


CONTEXTO_DIAS = 6  # barras dos dias anteriores, para comparar com o dia escolhido


def _inicio_balde(data, unidade):
    if unidade == 'semana':
        return data - timedelta(days=data.weekday())
    if unidade == 'mes':
        return data.replace(day=1)
    if unidade == 'ano':
        return data.replace(month=1, day=1)
    return data


def _proximo_balde(data, unidade):
    if unidade == 'semana':
        return data + timedelta(days=7)
    if unidade == 'mes':
        return _meses_atras(data, -1)
    if unidade == 'ano':
        return data.replace(year=data.year + 1)
    return data + timedelta(days=1)


def _inicios_dos_baldes(inicio, fim, unidade):
    baldes = []
    atual = _inicio_balde(inicio, unidade)
    while atual <= fim:
        baldes.append(atual)
        atual = _proximo_balde(atual, unidade)
    return baldes


def unidade_adequada(inicio, fim, unidade):
    """Sobe a unidade (dia → semana → mês → ano) se houver barras demais."""
    if unidade not in _ORDEM_UNIDADES:
        unidade = 'dia'
    indice = _ORDEM_UNIDADES.index(unidade)
    while (indice < len(_ORDEM_UNIDADES) - 1
           and len(_inicios_dos_baldes(inicio, fim, _ORDEM_UNIDADES[indice])) > _MAX_BALDES):
        indice += 1
    return _ORDEM_UNIDADES[indice]


def _rotulos_do_balde(inicio_balde, unidade, inicio, fim):
    de = max(inicio_balde, inicio)
    ate = min(_proximo_balde(inicio_balde, unidade) - timedelta(days=1), fim)
    if unidade == 'dia':
        return inicio_balde.strftime('%d/%m'), inicio_balde.strftime('%d/%m/%Y')
    if unidade == 'mes':
        return (f'{_MESES_CURTOS[inicio_balde.month - 1]}/{inicio_balde:%y}',
                f'{_MESES_CURTOS[inicio_balde.month - 1]}/{inicio_balde.year}')
    if unidade == 'ano':
        return str(inicio_balde.year), str(inicio_balde.year)
    return (de.strftime('%d/%m'),
            f'Semana de {de:%d/%m} a {ate:%d/%m/%Y}')


def _saida_em(registro):
    concluida, legado = registro
    if concluida is not None:
        return timezone.localtime(concluida).date() if timezone.is_aware(concluida) else concluida.date()
    return legado


def _movimento_entre(base, de, ate):
    """Datas de entrada e de saída (uma por processo) dentro de [de, ate]."""
    entradas = list(base.filter(data_entrada__gte=de, data_entrada__lte=ate)
                    .values_list('data_entrada', flat=True))
    saidas = [
        _saida_em(registro)
        for registro in base.filter(
            Q(saida_concluida_em__date__gte=de, saida_concluida_em__date__lte=ate)
            | Q(saida_concluida_em__isnull=True, data_saida__gte=de, data_saida__lte=ate)
        ).values_list('saida_concluida_em', 'data_saida')
    ]
    return entradas, [d for d in saidas if d is not None and de <= d <= ate]


def _variacao(atual, anterior):
    """Variação percentual em relação ao período anterior (None se não há base)."""
    if not anterior:
        return None
    return round(100 * (atual - anterior) / anterior)


def fluxo(inicio, fim, unidade='dia', contexto_dias=0, **filtros):
    """Série de entradas × saídas por dia, semana, mês ou ano.

    Entrada = data de entrada do processo. Saída = saída concluída (ou a data
    de saída do fluxo antigo). A linha de acervo é o que continua na CGM ao
    fim de cada intervalo, na mesma conta do estoque dos indicadores.

    Com `unidade='dia'` e um único dia (inicio == fim), os totais são só
    daquele dia; `contexto_dias` acrescenta barras dos dias anteriores para
    comparar, e `destaque` aponta a barra do dia escolhido.
    """
    if fim < inicio:
        inicio, fim = fim, inicio
    unidade = unidade_adequada(inicio, fim, unidade)
    modo_dia = unidade == 'dia' and inicio == fim
    inicio_grafico = inicio - timedelta(days=contexto_dias) if modo_dia else inicio
    base = aplicar_filtros(
        Processo.objects.filter(cancelado_em__isnull=True), **filtros)

    entradas_graf, saidas_graf = _movimento_entre(base, inicio_grafico, fim)
    inicios = _inicios_dos_baldes(inicio_grafico, fim, unidade)
    por_balde = {dia: [0, 0] for dia in inicios}
    for dia in entradas_graf:
        por_balde[_inicio_balde(dia, unidade)][0] += 1
    for dia in saidas_graf:
        por_balde[_inicio_balde(dia, unidade)][1] += 1
    entradas = [d for d in entradas_graf if inicio <= d <= fim]
    saidas = [d for d in saidas_graf if inicio <= d <= fim]

    vespera = inicio_grafico - timedelta(days=1)
    acervo = base.filter(data_entrada__lte=vespera).exclude(
        _saiu_ate(vespera)).count()
    estoque_inicial = acervo
    baldes = []
    for dia in inicios:
        if modo_dia and dia == inicio:
            estoque_inicial = acervo
        entrou, saiu = por_balde[dia]
        acervo += entrou - saiu
        rotulo, titulo = _rotulos_do_balde(dia, unidade, inicio_grafico, fim)
        baldes.append({
            'chave': dia.isoformat(), 'rotulo': rotulo, 'titulo': titulo,
            'entradas': entrou, 'saidas': saiu, 'saldo': entrou - saiu,
            'acervo': acervo,
        })

    dias = (fim - inicio).days + 1
    ant_fim = inicio - timedelta(days=1)
    ant_entradas, ant_saidas = _movimento_entre(
        base, ant_fim - timedelta(days=dias - 1), ant_fim)
    total_entradas, total_saidas = len(entradas), len(saidas)
    return {
        'unidade': unidade,
        'unidade_rotulo': dict(UNIDADES_FLUXO)[unidade],
        'modo_dia': modo_dia,
        'destaque': inicio.isoformat() if modo_dia else None,
        'rotulo_anterior': 'dia anterior' if dias == 1 else 'período anterior',
        'inicio': inicio.isoformat(),
        'fim': fim.isoformat(),
        'baldes': baldes,
        'totais': {
            'entradas': total_entradas,
            'saidas': total_saidas,
            'saldo': total_entradas - total_saidas,
            'estoque_inicial': estoque_inicial,
            'estoque_final': acervo,
            'pico_entradas': max((b['entradas'] for b in baldes), default=0),
            'pico_saidas': max((b['saidas'] for b in baldes), default=0),
        },
        'anterior': {
            'entradas': len(ant_entradas),
            'saidas': len(ant_saidas),
            'var_entradas': _variacao(total_entradas, len(ant_entradas)),
            'var_saidas': _variacao(total_saidas, len(ant_saidas)),
        },
    }


# --------------------------------------------------------------------------
# Tempos do fluxo (item 50)
# --------------------------------------------------------------------------

def _entrada(processo):
    if not processo.data_entrada:
        return None
    momento = datetime.combine(processo.data_entrada,
                               processo.hora_entrada or datetime.min.time())
    return timezone.make_aware(momento) if timezone.is_naive(momento) else momento


def _dias(inicio, fim):
    if not inicio or not fim:
        return None
    dias = (fim - inicio).total_seconds() / 86400
    return round(dias, 1) if dias >= 0 else None


def tempos_do_processo(processo):
    """Os cinco tempos do documento, em dias, derivados dos carimbos."""
    entrada = _entrada(processo)
    return {
        'em_fila': _dias(entrada, processo.data_hora_assumido),
        'analise': _dias(processo.data_hora_assumido, processo.liberado_assinatura_em),
        'pos_analise': _dias(processo.liberado_assinatura_em, processo.disponivel_retirada_em),
        'aguardando_retirada': _dias(processo.disponivel_retirada_em, processo.saida_concluida_em),
        'total': _dias(entrada, processo.saida_concluida_em),
    }


def barras_tempo(tempos):
    """Barras do tempo médio. O texto mostra o dia; a barra, a proporção."""
    etapas = (
        ('Em fila', 'em_fila', 'info'),
        ('Análise', 'analise', 'alerta'),
        ('Pós-análise', 'pos_analise', 'neutro'),
        ('Aguardando retirada', 'aguardando_retirada', 'info'),
        ('Total, da entrada à saída', 'total', 'ok'),
    )
    linhas = []
    for rotulo, chave, cor in etapas:
        valor = tempos.get(chave)
        linhas.append({
            'rotulo': rotulo,
            'valor': valor or 0,
            'texto': '—' if valor is None else str(valor).replace('.', ','),
            'cor': cor,
        })
    return _com_percentual(linhas)


def tempos_medios(inicio, fim, **filtros):
    """Média dos processos com saída concluída no período.

    Processos do acervo anterior à nova tramitação não têm os carimbos
    intermediários e só entram no tempo total quando houver saída
    registrada pelo fluxo novo.
    """
    consulta = aplicar_filtros(
        Processo.objects.filter(cancelado_em__isnull=True,
                                saida_concluida_em__date__gte=inicio,
                                saida_concluida_em__date__lte=fim), **filtros)
    acumulado = {chave: [] for chave in
                 ('em_fila', 'analise', 'pos_analise', 'aguardando_retirada', 'total')}
    total_processos = 0
    for processo in consulta.iterator():
        total_processos += 1
        for chave, valor in tempos_do_processo(processo).items():
            if valor is not None:
                acumulado[chave].append(valor)
    medias = {chave: (round(sum(v) / len(v), 1) if v else None)
              for chave, v in acumulado.items()}
    medias['processos'] = total_processos
    return medias
