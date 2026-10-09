# processos_app/services/exportacao_ativos.py
"""Exportação Excel dos processos ativos (em tramitação)."""

from django.db.models import Case, IntegerField, Q, Value, When
from django.db.models.functions import Coalesce

from processos_app.models import Processo

from . import permissions as perm
from . import tramitacao


def pode_exportar_ativos(usuario):
    """Protocolo e administrador — quem opera a lista de Processos Ativos."""
    return perm.eh_administrador(usuario) or perm.is_protocolo(usuario)


def filtros_de_request(request):
    termo = (request.GET.get('termo') or '').strip()
    prioridade = (request.GET.get('prioridade') or 'todas').strip()
    genero = (request.GET.get('genero') or 'todas').strip()
    especie = (request.GET.get('especie') or 'todas').strip()
    situacao = (request.GET.get('situacao') or 'todas').strip()
    aba_cgm = (request.GET.get('aba') or '').strip() == 'cgm'
    return {
        'termo': termo,
        'prioridade': prioridade or 'todas',
        'genero': genero or 'todas',
        'especie': especie or 'todas',
        'situacao': situacao or 'todas',
        'aba_cgm': aba_cgm,
    }


def _ordenar_fila(consulta):
    return consulta.annotate(
        _ordem_prioridade=Coalesce(
            'prioridade_fk__ordem',
            Case(
                When(prioridade='URGENTE', then=Value(10)),
                When(prioridade__in=['PRIORITARIO', 'SIM'], then=Value(20)),
                When(prioridade__in=['NORMAL', 'NAO'], then=Value(30)),
                default=Value(999),
                output_field=IntegerField(),
            ),
            output_field=IntegerField(),
        )
    ).order_by('_ordem_prioridade', 'data_entrada', 'hora_entrada')


def consultar_ativos(usuario, filtros):
    """Mesmo universo da tela Processos Ativos / Processos CGM."""
    from django.db.models import Exists, OuterRef

    from processos_app.models import EventoProcesso

    from . import secretaria_cgm as svc_cgm

    if filtros.get('aba_cgm'):
        if not svc_cgm.pode_ver_processos_cgm(usuario):
            return Processo.objects.none()
        consulta = svc_cgm.apenas_processos_cgm(tramitacao.ativos())
    else:
        # Reflexo da fila: Licitações/Liquidações com entrada pelo Protocolo.
        cadastro = EventoProcesso.objects.filter(
            processo_id=OuterRef('pk'),
            tipo='PROCESSO_CADASTRADO',
        )
        consulta = (
            tramitacao.ativos()
            .filter(genero__in=['LICITACOES_E_CONTRATOS', 'LIQUIDACOES'])
            .filter(Exists(cadastro))
            .exclude(observacao_protocolo__startswith='Entrada via Nova análise')
        )
        consulta = perm.filtrar_por_grupo(usuario, consulta)

    consulta = consulta.select_related(
        'analista_responsavel', 'prioridade_fk', 'secretaria_fk')

    termo = (filtros.get('termo') or '').strip()
    if termo:
        consulta = consulta.filter(
            Q(numero_processo__icontains=termo)
            | Q(secretaria__icontains=termo)
            | Q(objeto__icontains=termo)
            | Q(contratada__icontains=termo)
            | Q(tecnico__icontains=termo)
            | Q(valor__icontains=termo)
            | Q(periodo__icontains=termo)
        )

    prioridade = filtros.get('prioridade') or 'todas'
    if prioridade != 'todas':
        consulta = consulta.filter(prioridade=prioridade)

    genero = filtros.get('genero') or 'todas'
    if genero != 'todas':
        if not perm.pode_ver_grupo(usuario, genero):
            return consulta.none()
        consulta = consulta.filter(genero=genero)

    especie = filtros.get('especie') or 'todas'
    if especie != 'todas':
        consulta = consulta.filter(especie=especie)

    situacao = filtros.get('situacao') or 'todas'
    if situacao in dict(Processo.SITUACAO_TRAMITE_CHOICES):
        consulta = consulta.filter(situacao_tramite=situacao)

    return _ordenar_fila(consulta)
