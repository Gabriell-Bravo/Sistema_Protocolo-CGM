# processos_app/services/meus_processos.py
"""Processos com o analista agora e processos em que ele já atuou."""

from django.db.models import Max, Q
from django.utils import timezone

from ..models import EventoProcesso, Processo
from . import permissions as perm
from . import prazos

# Atos que contam como “trabalhei neste processo”.
TIPOS_TRABALHO = (
    'PROCESSO_ASSUMIDO',
    'LIBERADO_ASSINATURA',
    'ASSINATURA_DIRECIONADA',
    'ASSINATURA_REDIRECIONADA',
)


def _base_visivel(usuario):
    """Processos do grupo do analista (ou todos, se admin/gestão)."""
    return perm.filtrar_por_grupo(
        usuario,
        Processo.objects.select_related(
            'analista_responsavel', 'assinatura_direcionada_para',
            'prioridade_fk', 'especie_fk',
        ),
    )


def ids_comigo(usuario):
    """Processos que estão com o usuário agora."""
    return set(
        Processo.objects.filter(
            Q(situacao_tramite='EM_ANALISE', analista_responsavel=usuario)
            | Q(
                situacao_tramite='ASSINATURA_DIRECIONADA',
                assinatura_direcionada_para=usuario,
            )
        ).values_list('id', flat=True)
    )


def ids_trabalhados(usuario):
    """Processos em que o usuário registrou ato de análise."""
    return set(
        EventoProcesso.objects.filter(
            usuario=usuario,
            tipo__in=TIPOS_TRABALHO,
        ).values_list('processo_id', flat=True)
    )


def _ultimo_ato_por_processo(usuario, processo_ids):
    if not processo_ids:
        return {}
    linhas = (
        EventoProcesso.objects.filter(
            usuario=usuario,
            processo_id__in=processo_ids,
            tipo__in=TIPOS_TRABALHO,
        )
        .values('processo_id')
        .annotate(ultimo=Max('criado_em'))
    )
    return {linha['processo_id']: linha['ultimo'] for linha in linhas}


def listar(usuario, filtro='comigo', termo=''):
    """Devolve (processos, totais, filtro) para a tela Meus processos.

    filtro: comigo | feitos | todos
    """
    comigo = ids_comigo(usuario)
    trabalhados = ids_trabalhados(usuario)
    todos_ids = comigo | trabalhados
    visiveis = set(
        _base_visivel(usuario)
        .filter(id__in=todos_ids)
        .values_list('id', flat=True)
    )
    comigo &= visiveis
    trabalhados &= visiveis
    todos_ids = comigo | trabalhados

    if filtro == 'comigo':
        ids = comigo
    elif filtro == 'feitos':
        # Já atuou e não está mais com ele (histórico do que fez).
        ids = trabalhados - comigo
    else:
        filtro = 'todos'
        ids = todos_ids

    consulta = _base_visivel(usuario).filter(id__in=ids)
    termo = (termo or '').strip()
    if termo:
        consulta = consulta.filter(
            Q(numero_processo__icontains=termo)
            | Q(objeto__icontains=termo)
            | Q(contratada__icontains=termo)
            | Q(secretaria__icontains=termo)
        )

    processos = list(consulta)
    ultimos = _ultimo_ato_por_processo(usuario, [p.id for p in processos])
    hoje = timezone.localdate()

    for processo in processos:
        prazos.anotar(processo, hoje)
        processo.eh_comigo = processo.id in comigo
        processo.ja_trabalhei = processo.id in trabalhados
        processo.ultimo_ato_em = ultimos.get(processo.id)
        if processo.eh_comigo and processo.situacao_tramite == 'EM_ANALISE':
            processo.rotulo_meu = 'Com você agora'
            processo.classe_meu = 'badge--mine'
        elif (
            processo.eh_comigo
            and processo.situacao_tramite == 'ASSINATURA_DIRECIONADA'
        ):
            processo.rotulo_meu = 'Assinatura direcionada a você'
            processo.classe_meu = 'badge--mine'
        else:
            processo.rotulo_meu = processo.situacao_exibicao
            processo.classe_meu = 'badge--other'

    # Comigo primeiro; depois mais recente atuação; depois entrada.
    processos.sort(
        key=lambda p: (
            0 if p.eh_comigo else 1,
            -(p.ultimo_ato_em.timestamp() if p.ultimo_ato_em else 0),
            -(p.data_entrada.toordinal() if p.data_entrada else 0),
            -(p.id or 0),
        )
    )

    totais = {
        'comigo': len(comigo),
        'feitos': len(trabalhados - comigo),
        'todos': len(todos_ids),
    }
    return processos, totais, filtro
