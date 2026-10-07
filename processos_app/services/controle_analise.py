# processos_app/services/controle_analise.py
"""Controle de análise — processos de Licitações e Contratos a analisar."""

from django.db.models import Case, IntegerField, Q, When
from django.utils import timezone

from . import permissions as perm
from . import prazos
from . import tramitacao

FILTROS = (
    ('todos', 'Todos ativos'),
    ('disponiveis', 'Disponíveis'),
    ('em_analise', 'Em análise'),
    ('assinatura', 'Para assinar'),
)


def pode_consultar(usuario):
    """Analista de Licitações, Gestão e administrador."""
    if not usuario or not usuario.is_active:
        return False
    if perm.eh_administrador(usuario) or perm.is_gestao(usuario):
        return True
    return perm.grupo_do_analista(usuario) == perm.GRUPO_LICITACOES


def _ordenar_fila(consulta):
    """Urgente → Prioritário → Normal; dentro da faixa, entrada mais antiga."""
    return consulta.annotate(
        _prio=Case(
            When(prioridade_fk__codigo='URGENTE', then=0),
            When(prioridade='URGENTE', then=0),
            When(prioridade_fk__codigo='PRIORITARIO', then=1),
            When(prioridade='PRIORITARIO', then=1),
            default=2,
            output_field=IntegerField(),
        )
    ).order_by('_prio', 'data_entrada', 'hora_entrada', 'id')


def listar(usuario, filtro='todos', termo=''):
    """Lista processos ativos de Licitações e Contratos."""
    perm.assert_permissao(
        pode_consultar(usuario),
        'Somente analista de Licitações e Contratos consulta o Controle de análise.')

    base = (
        tramitacao.ativos()
        .filter(genero=perm.GRUPO_LICITACOES)
        .select_related(
            'analista_responsavel', 'assinatura_direcionada_para',
            'prioridade_fk', 'especie_fk',
        )
    )

    totais = {
        'todos': base.count(),
        'disponiveis': base.filter(
            situacao_tramite='DISPONIVEL',
            analista_responsavel__isnull=True,
        ).count(),
        'em_analise': base.filter(
            situacao_tramite__in=('EM_ANALISE', 'ASSINATURA_DIRECIONADA'),
        ).count(),
        'assinatura': base.filter(
            situacao_tramite='AGUARDANDO_ASSINATURA',
        ).count(),
    }

    filtro = filtro if filtro in dict(FILTROS) else 'todos'
    consulta = base
    if filtro == 'disponiveis':
        consulta = consulta.filter(
            situacao_tramite='DISPONIVEL',
            analista_responsavel__isnull=True,
        )
    elif filtro == 'em_analise':
        consulta = consulta.filter(
            situacao_tramite__in=('EM_ANALISE', 'ASSINATURA_DIRECIONADA'),
        )
    elif filtro == 'assinatura':
        consulta = consulta.filter(situacao_tramite='AGUARDANDO_ASSINATURA')

    termo = (termo or '').strip()
    if termo:
        consulta = consulta.filter(
            Q(numero_processo__icontains=termo)
            | Q(secretaria__icontains=termo)
            | Q(objeto__icontains=termo)
            | Q(contratada__icontains=termo)
            | Q(especie_fk__nome__icontains=termo)
            | Q(analista_responsavel__first_name__icontains=termo)
            | Q(analista_responsavel__username__icontains=termo)
        )

    processos = list(_ordenar_fila(consulta))
    hoje = timezone.localdate()
    for processo in processos:
        prazos.anotar(processo, hoje)
        responsavel = processo.analista_responsavel_id == usuario.id
        direcionado = processo.assinatura_direcionada_para_id == usuario.id
        processo.pode_editar_analise = perm.pode_analisar_processo(
            usuario, processo)
        processo.eh_comigo = (
            (processo.situacao_tramite == 'EM_ANALISE' and responsavel)
            or (processo.situacao_tramite == 'ASSINATURA_DIRECIONADA'
                and direcionado)
        )
        if processo.eh_comigo and processo.situacao_tramite == 'EM_ANALISE':
            processo.rotulo_controle = 'Com você'
            processo.classe_controle = 'badge--mine'
        elif processo.situacao_tramite == 'DISPONIVEL':
            processo.rotulo_controle = 'Disponível para análise'
            processo.classe_controle = 'badge--other'
        else:
            processo.rotulo_controle = processo.situacao_exibicao
            processo.classe_controle = 'badge--other'
    return processos, totais, filtro
