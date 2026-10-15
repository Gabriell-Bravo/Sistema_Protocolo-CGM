# processos_app/services/pendencias.py
"""
Pendências e Diligências (itens 25 a 34, 46).

Divisão de trabalho:

    ANALISTA  identifica tecnicamente a pendência e a registra
              -> nasce AGUARDANDO_ATENDIMENTO
    ANALISTA (reentrada)  verifica pendências antigas do mesmo nº
              -> pode marcar como corrigida (RESOLVIDA)
    ANALISTA (Liquidação) também vê pendências do Processo origem
              (campo processo_pagamento) quando o nº de pagamento difere
    GESTÃO / ADMIN  concluem a diligência quando a Secretaria atendeu
              -> RESOLVIDA (sem passar pelo analista)

Contatos intermediários (telefone, e-mail, ofício) não são registrados.
O fluxo antigo "Indicar atendimento → analista confirma" permanece no
código só para registros legados ainda em ATENDIMENTO_INDICADO.
"""

from django.db import transaction
from django.db.models import Q, Value
from django.db.models.functions import Replace
from django.utils import timezone

from ..models import Pendencia, Processo
from . import permissions as perm
from .eventos import registrar_evento_pendencia, registrar_diff
from .numeros import chaves_dupla_origem_pagamento
from .tramitacao import TransicaoInvalida


def _expr_numero_sem_ponto(campo):
    """Remove '.' e espaços do número gravado (para comparar com normalizar_numero)."""
    return Replace(
        Replace(campo, Value('.'), Value('')),
        Value(' '),
        Value(''),
    )


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


def _normalizar_texto(valor):
    return ' '.join((valor or '').split()).casefold()


def detalhe_historico(descricao, texto_pendencia):
    """Texto do histórico sem repetir o corpo da diligência.

    Importação fica só como 'Importada da planilha.'. Conclusão, cancelamento
    e o que ainda falta continuam. Cópia do texto da pendência some.
    """
    desc = (descricao or '').strip()
    if not desc:
        return ''
    if desc.casefold().startswith('importada da planilha'):
        return 'Importada da planilha.'
    pend = _normalizar_texto(texto_pendencia)
    norm = _normalizar_texto(desc)
    if pend and norm and (
            norm == pend
            or (len(norm) >= 40 and (norm in pend or pend.startswith(norm)))
            or (len(pend) >= 40 and norm.startswith(pend[:80]))):
        return ''
    return desc


def montar_historico(pendencia):
    """Linhas do histórico: ato, data, pessoa e detalhe curto."""
    linhas = []
    tem_resolvida = False
    for evento in pendencia.eventos.all():
        if evento.tipo == 'RESOLVIDA':
            tem_resolvida = True
        quem = ''
        if evento.usuario_id:
            quem = (
                evento.usuario.get_full_name() or evento.usuario.username)
        linhas.append({
            'titulo': evento.get_tipo_display(),
            'quando': evento.criado_em,
            'quem': quem,
            'detalhe': detalhe_historico(evento.descricao, pendencia.descricao),
        })
    if (pendencia.status == 'RESOLVIDA' and not tem_resolvida
            and getattr(pendencia, 'resolvida_por_id', None)):
        quem = (
            pendencia.resolvida_por.get_full_name()
            or pendencia.resolvida_por.username)
        linhas.append({
            'titulo': 'Resolvida',
            'quando': pendencia.resolvida_em,
            'quem': quem,
            'detalhe': f'Concluída por {quem}.',
        })
    return linhas


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
        pendencia.historico_linhas = montar_historico(pendencia)
    return pendencias


def fila_diligencias(status='AGUARDANDO_ATENDIMENTO'):
    """item 28 e item 33.

    A consulta parte da Pendencia, NÃO dos processos ativos: uma pendência
    pode continuar aberta depois de o processo já ter saído da CGM.

    AGUARDANDO_ATENDIMENTO (aba ativa): todas as ainda abertas.
    RESOLVIDA (Finalizados): só quando o processo não tem mais nenhuma aberta.
    """
    from django.db.models import Exists, OuterRef, Prefetch

    from ..models import EventoPendencia

    consulta = (Pendencia.objects
                .select_related('processo', 'responsavel_tecnico',
                                'atendimento_indicado_por', 'resolvida_por',
                                'criada_por')
                .prefetch_related(
                    Prefetch(
                        'eventos',
                        queryset=(
                            EventoPendencia.objects
                            .select_related('usuario')
                            .order_by('criado_em', 'id')
                        ),
                    ))
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


def numeros_vinculados_pendencia(processo):
    """Dupla normalizada: nº do processo + Processo origem/pagamento.

    Em Liquidação o nº da tela costuma ser o de pagamento e a origem fica
    em processo_pagamento — mas os campos às vezes vêm invertidos. Por isso
    os dois entram no mesmo conjunto (ordem irrelevante).
    18.245/2025 e 18245/2025 contam como o mesmo número.
    """
    return chaves_dupla_origem_pagamento(processo)


def _pendencias_por_numeros_normalizados(processo, chaves):
    """Pendências cujo processo toca a dupla em qualquer um dos dois campos."""
    if not chaves:
        return Pendencia.objects.none()
    return (Pendencia.objects
            .annotate(
                _num_norm=_expr_numero_sem_ponto(
                    'processo__numero_processo'),
                _pag_norm=_expr_numero_sem_ponto(
                    'processo__processo_pagamento'),
            )
            .filter(Q(_num_norm__in=chaves) | Q(_pag_norm__in=chaves))
            .exclude(processo_id=processo.id)
            .exclude(status='CANCELADA')
            .select_related(
                'processo', 'responsavel_tecnico', 'resolvida_por')
            .order_by('criada_em'))


def abertas_de_passagens_anteriores(processo):
    """Pendências ainda abertas de passagens anteriores (dupla origem/pagamento)."""
    return (pendencias_de_passagens_anteriores(processo)
            .filter(status__in=Pendencia.STATUS_ABERTOS))


def pendencias_de_passagens_anteriores(processo):
    """Passagem anterior: abertas e já corrigidas (para não sumirem da análise).

    Liga pela dupla origem ↔ pagamento (ordem dos campos irrelevante).
    Números com ou sem ponto milhar são tratados como iguais.
    """
    return _pendencias_por_numeros_normalizados(
        processo, numeros_vinculados_pendencia(processo))


def abertas_do_mesmo_numero(processo):
    """Pendências abertas da mesma dupla origem/pagamento."""
    return (_pendencias_por_numeros_normalizados(
                processo, numeros_vinculados_pendencia(processo))
            .filter(status__in=Pendencia.STATUS_ABERTOS))


def mensagem_aviso_ao_assumir(processo):
    """Texto do alerta ao assumir, ou None se não houver diligência aberta."""
    if not abertas_do_mesmo_numero(processo).exists():
        return None
    return (
        'Este processo possui diligências em aberto. '
        'Verifique na lista abaixo se já foram corrigidas.'
    )


@transaction.atomic
def verificar_correcao(pendencia_id, usuario, processo_atual_id,
                       itens_concluidos=None):
    """Salva marcações; só conclui a diligência quando todos os itens estão ok.

    Marcação parcial mantém a diligência aberta (não vai para Finalizados).
    """
    pendencia = _travar(pendencia_id)
    processo_atual = (Processo.objects.select_for_update()
                      .filter(id=processo_atual_id).first())
    if processo_atual is None:
        raise TransicaoInvalida('Processo não encontrado.')

    perm.assert_permissao(
        perm.pode_verificar_correcao_pendencia(
            usuario, pendencia, processo_atual),
        'Só o analista responsável desta passagem verifica a correção '
        'das pendências anteriores.')

    if not pendencia.esta_aberta:
        raise TransicaoInvalida(
            f'Diligência em "{pendencia.get_status_display()}" não pode '
            'ser atualizada agora.')

    validos, escolhidos = _itens_marcados(pendencia, itens_concluidos)
    pendencia.itens_concluidos = escolhidos
    completa = (not validos) or set(validos).issubset(set(escolhidos))

    if not completa:
        # Parcial: guarda os itens, mantém aberta (não vai a Finalizados).
        pendencia.save(update_fields=['itens_concluidos'])
        return pendencia, False

    pendencia.status = 'RESOLVIDA'
    pendencia.resolvida_em = timezone.now()
    pendencia.resolvida_por = usuario
    if pendencia.atendimento_indicado_em is None:
        pendencia.atendimento_indicado_em = pendencia.resolvida_em
        pendencia.atendimento_indicado_por = usuario
    pendencia.save(update_fields=[
        'status', 'resolvida_em', 'resolvida_por', 'itens_concluidos',
        'atendimento_indicado_em', 'atendimento_indicado_por'])

    detalhe = (
        f'Corrigida na análise da passagem atual por '
        f'{perm.nome_usuario(usuario)}.')
    if validos:
        detalhe += f' {len(escolhidos)} de {len(validos)} item(ns).'
    registrar_evento_pendencia(pendencia, 'RESOLVIDA', usuario, detalhe)
    return pendencia, True


def _travar(pendencia_id):
    pendencia = (Pendencia.objects.select_for_update()
                 .filter(id=pendencia_id).first())
    if pendencia is None:
        raise TransicaoInvalida('Diligência não encontrada.')
    return pendencia
