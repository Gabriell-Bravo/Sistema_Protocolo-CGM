# processos_app/services/pendencias.py
"""
Pendências e Diligências (itens 25 a 34, 46).

Divisão de trabalho, conforme o documento:

    ANALISTA  identifica tecnicamente a pendência e a registra
              -> nasce AGUARDANDO_ATENDIMENTO
    GESTÃO    faz as diligências FORA do sistema (telefone, e-mail,
              ofício) e, quando julga que houve atendimento suficiente
              para nova análise, usa "Indicar atendimento"
    ANALISTA  confirma a resolução, ou devolve como insuficiente

A Gestão não conclui tecnicamente a pendência (item 25).
Contatos intermediários não são registrados (itens 25 e 46).
"""

from django.db import transaction
from django.utils import timezone

from ..models import Pendencia, Processo
from . import permissions as perm
from .eventos import registrar_evento_pendencia, registrar_diff
from .tramitacao import TransicaoInvalida


# --------------------------------------------------------------------------
# Analista: criar
# --------------------------------------------------------------------------

@transaction.atomic
def criar(processo_id, usuario, descricao):
    """A pendência nasce da análise técnica, em AGUARDANDO_ATENDIMENTO."""
    processo = (Processo.objects.select_for_update()
                .filter(id=processo_id).first())
    if processo is None:
        raise TransicaoInvalida('Processo não encontrado.')

    perm.assert_permissao(
        perm.pode_criar_pendencia(usuario, processo),
        'Só o analista responsável pode incluir pendências.')

    descricao = (descricao or '').strip()
    if not descricao:
        raise TransicaoInvalida('Descreva a pendência antes de adicionar.')

    pendencia = Pendencia.objects.create(
        processo=processo,
        descricao=descricao,
        criada_por=usuario,
        # item 27: fixado na criação, permanece mesmo que o processo mude
        # de estado ou já tenha saído fisicamente da CGM.
        responsavel_tecnico=usuario,
        status='AGUARDANDO_ATENDIMENTO',
    )
    registrar_evento_pendencia(pendencia, 'CRIADA', usuario, descricao)
    registrar_diff(processo, 'pendencia_adicionada', '', descricao, usuario)
    return pendencia


# --------------------------------------------------------------------------
# Gestão: indicar atendimento
# --------------------------------------------------------------------------

@transaction.atomic
def indicar_atendimento(pendencia_id, usuario):
    """AGUARDANDO_ATENDIMENTO -> ATENDIMENTO_INDICADO (item 29).

    A Gestão sinaliza que houve atendimento suficiente para nova análise
    técnica. Não resolve a pendência.
    """
    pendencia = _travar(pendencia_id)

    perm.assert_permissao(
        perm.pode_indicar_atendimento(usuario),
        'Somente a Gestão pode indicar atendimento.')

    if pendencia.status != 'AGUARDANDO_ATENDIMENTO':
        raise TransicaoInvalida(
            f'Pendência em "{pendencia.get_status_display()}" não aguarda '
            'atendimento.')

    pendencia.status = 'ATENDIMENTO_INDICADO'
    pendencia.atendimento_indicado_em = timezone.now()
    pendencia.atendimento_indicado_por = usuario
    pendencia.save(update_fields=['status', 'atendimento_indicado_em',
                                  'atendimento_indicado_por'])

    registrar_evento_pendencia(
        pendencia, 'ATENDIMENTO_INDICADO', usuario,
        f'Atendimento indicado por {perm.nome_usuario(usuario)}.')
    return pendencia


# --------------------------------------------------------------------------
# Analista: confirmar ou devolver
# --------------------------------------------------------------------------

@transaction.atomic
def confirmar_resolucao(pendencia_id, usuario):
    """ATENDIMENTO_INDICADO -> RESOLVIDA (item 30).

    Não exige texto adicional: usuário e horário são automáticos.
    """
    pendencia = _travar(pendencia_id)

    perm.assert_permissao(
        perm.pode_resolver_pendencia(usuario, pendencia),
        'Só o responsável técnico pode confirmar a resolução.')

    if pendencia.status != 'ATENDIMENTO_INDICADO':
        raise TransicaoInvalida(
            f'Pendência em "{pendencia.get_status_display()}" não pode ser '
            'resolvida agora.')

    pendencia.status = 'RESOLVIDA'
    pendencia.resolvida_em = timezone.now()
    pendencia.resolvida_por = usuario
    pendencia.save(update_fields=['status', 'resolvida_em', 'resolvida_por'])

    registrar_evento_pendencia(
        pendencia, 'RESOLVIDA', usuario,
        f'Resolução confirmada por {perm.nome_usuario(usuario)}.')
    return pendencia


@transaction.atomic
def atendimento_insuficiente(pendencia_id, usuario, o_que_falta):
    """ATENDIMENTO_INDICADO -> AGUARDANDO_ATENDIMENTO (item 30).

    A pendência reaparece sozinha na fila de Diligências da Gestão: não
    há reabertura manual.
    """
    pendencia = _travar(pendencia_id)

    perm.assert_permissao(
        perm.pode_resolver_pendencia(usuario, pendencia),
        'Só o responsável técnico pode avaliar o atendimento.')

    if pendencia.status != 'ATENDIMENTO_INDICADO':
        raise TransicaoInvalida(
            'Só é possível avaliar uma pendência com atendimento indicado.')

    o_que_falta = (o_que_falta or '').strip()
    if not o_que_falta:
        raise TransicaoInvalida('Informe o que ainda precisa ser atendido.')

    pendencia.status = 'AGUARDANDO_ATENDIMENTO'
    pendencia.atendimento_indicado_em = None
    pendencia.atendimento_indicado_por = None
    pendencia.save(update_fields=['status', 'atendimento_indicado_em',
                                  'atendimento_indicado_por'])

    registrar_evento_pendencia(
        pendencia, 'ATENDIMENTO_INSUFICIENTE', usuario, o_que_falta)
    return pendencia


# --------------------------------------------------------------------------
# Cancelamento (item 32)
# --------------------------------------------------------------------------

@transaction.atomic
def cancelar(pendencia_id, usuario, motivo):
    """Pendência não é apagada. Cadastrada indevidamente, é cancelada."""
    pendencia = _travar(pendencia_id)

    autorizado = (
        perm.pode_resolver_pendencia(usuario, pendencia)
        or perm.is_gestao(usuario)
    )
    perm.assert_permissao(
        autorizado,
        'Só o responsável técnico ou a Gestão podem cancelar a pendência.')

    motivo = (motivo or '').strip()
    if not motivo:
        raise TransicaoInvalida('Informe o motivo do cancelamento.')
    if pendencia.status in ('RESOLVIDA', 'CANCELADA'):
        raise TransicaoInvalida(
            f'Pendência já está em "{pendencia.get_status_display()}".')

    pendencia.status = 'CANCELADA'
    pendencia.cancelada_em = timezone.now()
    pendencia.cancelada_por = usuario
    pendencia.motivo_cancelamento = motivo
    pendencia.save(update_fields=['status', 'cancelada_em', 'cancelada_por',
                                  'motivo_cancelamento'])

    registrar_evento_pendencia(pendencia, 'CANCELADA', usuario, motivo)
    return pendencia


# --------------------------------------------------------------------------
# Consultas
# --------------------------------------------------------------------------

def fila_diligencias(status='AGUARDANDO_ATENDIMENTO'):
    """item 28 e item 33.

    A consulta parte da Pendencia, NÃO dos processos ativos: uma pendência
    pode continuar aberta depois de o processo já ter saído da CGM.
    """
    consulta = (Pendencia.objects
                .select_related('processo', 'responsavel_tecnico',
                                'atendimento_indicado_por')
                .order_by('criada_em'))
    if status == 'ABERTAS':
        return consulta.filter(status__in=Pendencia.STATUS_ABERTOS)
    if status:
        return consulta.filter(status=status)
    return consulta


def atendimentos_indicados(usuario):
    """item 30: o que voltou para o analista avaliar."""
    return (Pendencia.objects
            .filter(responsavel_tecnico=usuario,
                    status='ATENDIMENTO_INDICADO')
            .select_related('processo', 'atendimento_indicado_por')
            .order_by('atendimento_indicado_em'))


def total_atendimentos_indicados(usuario):
    if not perm.is_analista(usuario):
        return 0
    return atendimentos_indicados(usuario).count()


def abertas_de_passagens_anteriores(processo):
    """item 34: mesmo número de processo, passagem anterior, somente leitura.

    Não duplica pendência: apenas mostra o que ficou em aberto quando o
    processo esteve aqui antes.
    """
    return (Pendencia.objects
            .filter(processo__numero_processo=processo.numero_processo,
                    status__in=Pendencia.STATUS_ABERTOS)
            .exclude(processo_id=processo.id)
            .select_related('processo', 'responsavel_tecnico')
            .order_by('criada_em'))


def _travar(pendencia_id):
    pendencia = (Pendencia.objects.select_for_update()
                 .filter(id=pendencia_id).first())
    if pendencia is None:
        raise TransicaoInvalida('Pendência não encontrada.')
    return pendencia
