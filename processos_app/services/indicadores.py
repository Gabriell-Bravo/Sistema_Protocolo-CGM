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

def cards(referencia=None):
    hoje = referencia or timezone.localdate()
    ativos = tramitacao.ativos()

    por_situacao = dict(ativos.values_list('situacao_tramite')
                        .annotate(total=Count('id')).values_list('situacao_tramite', 'total'))

    vencidos = vencendo_hoje = 0
    for processo in ativos.only('id', 'data_entrada', 'prioridade'):
        dias = prazos.dias_restantes(processo, hoje)
        if dias is None:
            continue
        if dias < 0:
            vencidos += 1
        elif dias == 0:
            vencendo_hoje += 1

    return [
        {'rotulo': 'Em tramitação', 'valor': sum(por_situacao.values()),
         'icone': 'account_tree', 'cor': 'primary', 'url': _url('listar_processos')},
        {'rotulo': 'Disponíveis para análise', 'valor': por_situacao.get('DISPONIVEL', 0),
         'icone': 'front_hand', 'cor': 'success', 'url': _url('gestao_processos', 'filtro=disponiveis')},
        {'rotulo': 'Em análise', 'valor': por_situacao.get('EM_ANALISE', 0)
                                          + por_situacao.get('ASSINATURA_DIRECIONADA', 0),
         'icone': 'manage_accounts', 'cor': 'violet', 'url': _url('gestao_processos', 'filtro=em_analise')},
        {'rotulo': 'Liberados para assinatura', 'valor': por_situacao.get('AGUARDANDO_ASSINATURA', 0),
         'icone': 'draw', 'cor': 'primary', 'url': _url('gestao_liberados_assinatura')},
        {'rotulo': 'Disponíveis para retirada', 'valor': por_situacao.get('DISPONIVEL_RETIRADA', 0),
         'icone': 'assignment_return', 'cor': 'success',
         'url': _url('listar_processos', 'situacao=DISPONIVEL_RETIRADA')},
        {'rotulo': 'Vencidos', 'valor': vencidos, 'icone': 'running_with_errors',
         'cor': 'danger', 'url': _url('gestao_processos', 'filtro=vencidos')},
        {'rotulo': 'Vencendo hoje', 'valor': vencendo_hoje, 'icone': 'event_busy',
         'cor': 'warning', 'url': _url('gestao_processos', 'filtro=vence_hoje')},
        {'rotulo': 'Urgentes', 'valor': ativos.filter(prioridade='URGENTE').count(),
         'icone': 'priority_high', 'cor': 'danger', 'url': _url('gestao_processos', 'filtro=urgentes')},
        {'rotulo': 'Diligências', 'icone': 'campaign', 'cor': 'warning',
         'valor': Pendencia.objects.filter(status='AGUARDANDO_ATENDIMENTO').count(),
         'url': _url('gestao_diligencias')},
        {'rotulo': 'Atendimentos indicados', 'icone': 'assignment_turned_in', 'cor': 'violet',
         'valor': Pendencia.objects.filter(status='ATENDIMENTO_INDICADO').count(),
         'url': _url('gestao_diligencias', 'status=ATENDIMENTO_INDICADO')},
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
            .only('id', 'data_entrada', 'prioridade'))
        vencidos = sum(1 for p in em_analise
                       if (prazos.dias_restantes(p, hoje) or 0) < 0)
        concluidos = Processo.objects.filter(
            analista_responsavel=analista,
            liberado_assinatura_em__date__gte=inicio,
            liberado_assinatura_em__date__lte=fim).count()
        linhas.append({
            'nome': perm.nome_usuario(analista),
            'grupo': Processo.GENERO_LABELS.get(perm.grupo_do_analista(analista) or '', '—'),
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
    return {
        'recebidos': recebidos.count(),
        'liberados_assinatura': liberados.count(),
        'saidas_concluidas': saidas.count(),
        'estoque_inicial': estoque(inicio - timedelta(days=1)),
        'estoque_final': estoque(fim),
        'retornos': retornos,
        'por_grupo': [
            {'rotulo': rotulos.get(l['genero'], l['genero'] or '—'), 'total': l['total']}
            for l in recebidos.values('genero').annotate(total=Count('id')).order_by('-total')
        ],
        'por_secretaria': list(recebidos.values('secretaria')
                               .annotate(total=Count('id')).order_by('-total', 'secretaria')),
        'por_especie': list(recebidos.values('especie')
                            .annotate(total=Count('id')).order_by('-total', 'especie')),
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
