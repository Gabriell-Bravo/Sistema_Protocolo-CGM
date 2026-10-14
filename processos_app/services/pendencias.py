# processos_app/services/pendencias.py
"""
Pendências e Diligências (itens 25 a 34, 46).

Divisão de trabalho:

    ANALISTA  identifica tecnicamente a pendência e a registra
              -> nasce AGUARDANDO_ATENDIMENTO
    GESTÃO / ADMIN  concluem a diligência quando a Secretaria atendeu
              -> RESOLVIDA (sem passar pelo analista)

Contatos intermediários (telefone, e-mail, ofício) não são registrados.
O fluxo antigo "Indicar atendimento → analista confirma" permanece no
código só para registros legados ainda em ATENDIMENTO_INDICADO.
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
        'Só o analista responsável pode incluir diligências.')

    descricao = (descricao or '').strip()
    if not descricao:
        raise TransicaoInvalida('Descreva a diligência antes de adicionar.')

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
# Gestão / Admin: concluir direto
# --------------------------------------------------------------------------

def _itens_marcados(pendencia, itens_concluidos):
    from .diligencia_texto import separar_itens

    validos = separar_itens(pendencia.descricao)
    if not validos:
        return [], []
    # None = conclusão programática (marca todos). Lista vazia = nenhum marcado.
    if itens_concluidos is None:
        return validos, validos
    escolhidos = []
    vistos = set()
    for item in itens_concluidos:
        item = (item or '').strip()
        if item in validos and item not in vistos:
            escolhidos.append(item)
            vistos.add(item)
    return validos, escolhidos


@transaction.atomic
def concluir(pendencia_id, usuario, itens_concluidos=None):
    """Gestão/admin concluem a diligência → RESOLVIDA.

    Aceita AGUARDANDO_ATENDIMENTO e o legado ATENDIMENTO_INDICADO.
    """
    pendencia = _travar(pendencia_id)

    perm.assert_permissao(
        perm.pode_concluir_pendencia(usuario),
        'Somente a Gestão ou o administrador podem concluir a diligência.')

    if pendencia.status not in (
            'AGUARDANDO_ATENDIMENTO', 'ATENDIMENTO_INDICADO'):
        raise TransicaoInvalida(
            f'Diligência em "{pendencia.get_status_display()}" não pode '
            'ser concluída agora.')

    validos, escolhidos = _itens_marcados(pendencia, itens_concluidos)
    pendencia.status = 'RESOLVIDA'
    pendencia.resolvida_em = timezone.now()
    pendencia.resolvida_por = usuario
    pendencia.itens_concluidos = escolhidos
    if pendencia.atendimento_indicado_em is None:
        pendencia.atendimento_indicado_em = pendencia.resolvida_em
        pendencia.atendimento_indicado_por = usuario
    pendencia.save(update_fields=[
        'status', 'resolvida_em', 'resolvida_por', 'itens_concluidos',
        'atendimento_indicado_em', 'atendimento_indicado_por'])

    detalhe = f'Diligência concluída por {perm.nome_usuario(usuario)}.'
    if validos:
        detalhe += (
            f' {len(escolhidos)} de {len(validos)} item(ns) marcado(s).')
    registrar_evento_pendencia(pendencia, 'RESOLVIDA', usuario, detalhe)
    return pendencia


@transaction.atomic
def indicar_atendimento(pendencia_id, usuario, itens_concluidos=None):
    """Legado: AGUARDANDO_ATENDIMENTO -> ATENDIMENTO_INDICADO.

    Preferir `concluir`. Mantido para testes e registros antigos.
    """
    from .diligencia_texto import separar_itens

    pendencia = _travar(pendencia_id)

    perm.assert_permissao(
        perm.pode_indicar_atendimento(usuario),
        'Somente a Gestão ou o administrador podem indicar atendimento.')

    if pendencia.status != 'AGUARDANDO_ATENDIMENTO':
        raise TransicaoInvalida(
            f'Diligência em "{pendencia.get_status_display()}" não aguarda '
            'atendimento.')

    validos = separar_itens(pendencia.descricao)
    escolhidos = []
    vistos = set()
    for item in itens_concluidos or []:
        item = (item or '').strip()
        if item in validos and item not in vistos:
            escolhidos.append(item)
            vistos.add(item)

    pendencia.status = 'ATENDIMENTO_INDICADO'
    pendencia.atendimento_indicado_em = timezone.now()
    pendencia.atendimento_indicado_por = usuario
    pendencia.itens_concluidos = escolhidos
    pendencia.save(update_fields=[
        'status', 'atendimento_indicado_em', 'atendimento_indicado_por',
        'itens_concluidos'])

    detalhe = f'Atendimento indicado por {perm.nome_usuario(usuario)}.'
    if validos:
        detalhe += f' {len(escolhidos)} de {len(validos)} item(ns) marcado(s) como atendido(s).'
    registrar_evento_pendencia(
        pendencia, 'ATENDIMENTO_INDICADO', usuario, detalhe)
    return pendencia


@transaction.atomic
def desfazer_indicacao(pendencia_id, usuario):
    """ATENDIMENTO_INDICADO -> AGUARDANDO_ATENDIMENTO, só o administrador.

    Desfaz uma indicação lançada por engano, sem a conta do analista.
    As marcações do checklist saem junto: a Gestão indica de novo.
    """
    pendencia = _travar(pendencia_id)

    perm.assert_permissao(
        perm.pode_desfazer_indicacao_atendimento(usuario),
        'Somente o administrador pode desfazer a indicação de atendimento.')

    if pendencia.status != 'ATENDIMENTO_INDICADO':
        raise TransicaoInvalida(
            f'Diligência em "{pendencia.get_status_display()}" não tem '
            'indicação para desfazer.')

    pendencia.status = 'AGUARDANDO_ATENDIMENTO'
    pendencia.atendimento_indicado_em = None
    pendencia.atendimento_indicado_por = None
    pendencia.itens_concluidos = []
    pendencia.save(update_fields=[
        'status', 'atendimento_indicado_em', 'atendimento_indicado_por',
        'itens_concluidos'])

    registrar_evento_pendencia(
        pendencia, 'INDICACAO_DESFEITA', usuario,
        f'Indicação de atendimento desfeita por {perm.nome_usuario(usuario)}.')
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
            f'Diligência em "{pendencia.get_status_display()}" não pode ser '
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
            'Só é possível avaliar uma diligência com atendimento indicado.')

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

    perm.assert_permissao(
        perm.pode_cancelar_pendencia(usuario, pendencia),
        'Só o responsável técnico, a Gestão ou o administrador podem '
        'cancelar a diligência.')

    motivo = (motivo or '').strip()
    if not motivo:
        raise TransicaoInvalida('Informe o motivo do cancelamento.')
    if pendencia.status in ('RESOLVIDA', 'CANCELADA'):
        raise TransicaoInvalida(
            f'Diligência já está em "{pendencia.get_status_display()}".')

    pendencia.status = 'CANCELADA'
    pendencia.cancelada_em = timezone.now()
    pendencia.cancelada_por = usuario
    pendencia.motivo_cancelamento = motivo
    pendencia.save(update_fields=['status', 'cancelada_em', 'cancelada_por',
                                  'motivo_cancelamento'])

    registrar_evento_pendencia(pendencia, 'CANCELADA', usuario, motivo)
    return pendencia


@transaction.atomic
def editar_descricao(pendencia_id, usuario, nova_descricao):
    """Corrige o texto de uma diligência ainda aberta."""
    pendencia = _travar(pendencia_id)

    perm.assert_permissao(
        perm.pode_editar_pendencia(usuario, pendencia),
        'Só o responsável técnico, a Gestão ou o administrador podem '
        'editar a diligência.')

    nova = (nova_descricao or '').strip()
    if not nova:
        raise TransicaoInvalida('Descreva a diligência antes de salvar.')
    if pendencia.status in ('RESOLVIDA', 'CANCELADA'):
        raise TransicaoInvalida(
            f'Diligência em "{pendencia.get_status_display()}" não pode '
            'ser editada.')

    anterior = pendencia.descricao or ''
    if anterior.strip() == nova:
        return pendencia

    pendencia.descricao = nova
    pendencia.save(update_fields=['descricao'])
    registrar_diff(
        pendencia.processo, 'pendencia_editada', anterior, nova, usuario)
    return pendencia


# --------------------------------------------------------------------------
# Consultas
# --------------------------------------------------------------------------

def progresso_processo(processo_id):
    """(resolvidas, total) excluindo canceladas — ex.: 3/5 completos."""
    base = Pendencia.objects.filter(processo_id=processo_id).exclude(
        status='CANCELADA')
    total = base.count()
    resolvidas = base.filter(status='RESOLVIDA').count()
    return resolvidas, total


def anotar_progresso(pendencias):
    """Anota progresso do processo (diligências) e dos itens do checklist."""
    from .diligencia_texto import separar_itens

    ids = {p.processo_id for p in pendencias}
    if not ids:
        return pendencias
    from django.db.models import Count, Q
    mapa = {
        row['processo_id']: (row['resolvidas'], row['total'])
        for row in (
            Pendencia.objects.filter(processo_id__in=ids)
            .exclude(status='CANCELADA')
            .values('processo_id')
            .annotate(
                total=Count('id'),
                resolvidas=Count('id', filter=Q(status='RESOLVIDA')),
            )
        )
    }
    for pendencia in pendencias:
        resolvidas, total = mapa.get(pendencia.processo_id, (0, 0))
        pendencia.progresso_resolvidas = resolvidas
        pendencia.progresso_total = total
        # Só exibe quando o processo tem mais de uma diligência —
        # "0/1 completo" ao lado de vários itens do checklist confundia.
        pendencia.progresso_rotulo = (
            f'{resolvidas}/{total} diligência{"s" if total != 1 else ""}'
            if total > 1 else ''
        )
        pendencia.processo_todas_completas = (
            total > 0 and resolvidas == total)

        itens = separar_itens(pendencia.descricao)
        feitos = set(pendencia.itens_concluidos or [])
        marcados = sum(1 for item in itens if item in feitos)
        pendencia.itens_total = len(itens)
        pendencia.itens_feitos = marcados
        pendencia.itens_rotulo = (
            f'{marcados}/{len(itens)} itens'
            if len(itens) > 1 else ''
        )
    return pendencias


def fila_diligencias(status='AGUARDANDO_ATENDIMENTO'):
    """item 28 e item 33.

    A consulta parte da Pendencia, NÃO dos processos ativos: uma pendência
    pode continuar aberta depois de o processo já ter saído da CGM.

    AGUARDANDO_ATENDIMENTO (aba ativa): todas as ainda abertas.
    RESOLVIDA (Finalizados): só quando o processo não tem mais nenhuma aberta.
    """
    from django.db.models import Exists, OuterRef

    consulta = (Pendencia.objects
                .select_related('processo', 'responsavel_tecnico',
                                'atendimento_indicado_por', 'resolvida_por')
                .order_by('criada_em'))
    if status == 'ABERTAS' or status == 'AGUARDANDO_ATENDIMENTO':
        return consulta.filter(status__in=Pendencia.STATUS_ABERTOS)
    if status == 'RESOLVIDA':
        ainda_aberta = Pendencia.objects.filter(
            processo_id=OuterRef('processo_id'),
            status__in=Pendencia.STATUS_ABERTOS,
        )
        return (
            consulta.filter(status='RESOLVIDA')
            .annotate(_tem_aberta=Exists(ainda_aberta))
            .filter(_tem_aberta=False)
        )
    if status == 'ATENDIMENTO_INDICADO':
        # Aba removida da UI; mantém filtro para URLs antigas.
        return consulta.filter(status='ATENDIMENTO_INDICADO')
    if status:
        return consulta.filter(status=status)
    return consulta


def filtrar_por_termo(consulta, termo):
    """Busca livre na fila de diligências (processo, secretaria, texto, analista)."""
    termo = (termo or '').strip()
    if not termo:
        return consulta
    from django.db.models import Q
    return consulta.filter(
        Q(descricao__icontains=termo) |
        Q(processo__numero_processo__icontains=termo) |
        Q(processo__secretaria__icontains=termo) |
        Q(processo__objeto__icontains=termo) |
        Q(processo__contratada__icontains=termo) |
        Q(processo__especie__icontains=termo) |
        Q(responsavel_tecnico__first_name__icontains=termo) |
        Q(responsavel_tecnico__last_name__icontains=termo) |
        Q(responsavel_tecnico__username__icontains=termo) |
        Q(motivo_cancelamento__icontains=termo)
    )


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
        raise TransicaoInvalida('Diligência não encontrada.')
    return pendencia
