# processos_app/services/tramitacao.py
"""
Máquina de estados do processo (itens 6, 8, 10, 11, 13, 14, 15, 16, 35).

Toda transição de `situacao_tramite` acontece AQUI. Nenhuma view, nenhum
form e nenhum endpoint genérico pode alterar esse campo diretamente
(item 52).

Cada operação valida, nesta ordem:
    1. quem pode          -> services.permissions
    2. estado atual       -> ESTADOS_PERMITIDOS da operação
    3. próximo estado
    4. efeito
    5. evento de histórico -> services.eventos

Fluxo normal
    DISPONIVEL -> EM_ANALISE -> AGUARDANDO_ASSINATURA
    -> DISPONIVEL_RETIRADA -> SAIDA_CONCLUIDA

Fluxo com direcionamento
    DISPONIVEL -> EM_ANALISE -> ASSINATURA_DIRECIONADA
    -> AGUARDANDO_ASSINATURA -> DISPONIVEL_RETIRADA -> SAIDA_CONCLUIDA

Não existe estado ASSINADO: a assinatura do Controlador é física (item 6).

Enquanto a casa não usa a tramitação completa no dia a dia, o Protocolo
pode registrar a saída de qualquer processo ainda na CGM
(`registrar_saida_direta`), sem passar por análise nem assinatura.
"""

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from ..models import Pendencia, Processo, UrgenciaRecorrente
from . import permissions as perm
from . import prazos
from .eventos import registrar_evento, registrar_diff, registrar_evento_pendencia


class TransicaoInvalida(ValidationError):
    """Operação incompatível com o estado atual do processo."""


# --------------------------------------------------------------------------
# Completude da análise
# --------------------------------------------------------------------------
# Campos que precisam estar preenchidos para o processo sair das mãos do
# analista. Vale tanto para "Liberar para assinatura" quanto para
# "Direcionar para outro analista".
#
# Licitações e Contratos não exige esses campos: o registro da análise é
# o arquivo anexado. Liquidações exige status e destino; o número do
# relatório é gerado ao encaminhar para o Controlador.
#
# Para mudar a exigência, altere só estas listas.
CAMPOS_OBRIGATORIOS_LIBERACAO = {
    'LICITACOES_E_CONTRATOS': [],
    'LIQUIDACOES': [
        ('status_analise', 'Status da análise'),
        ('destino', 'Destino'),
    ],
}
CAMPOS_OBRIGATORIOS_PADRAO = CAMPOS_OBRIGATORIOS_LIBERACAO['LIQUIDACOES']


def _eh_licitacao(processo):
    return processo.grupo == perm.GRUPO_LICITACOES


def campos_faltantes(processo):
    """O que ainda falta para encaminhar à assinatura."""
    if _eh_licitacao(processo):
        if not processo.anexos.exists():
            return ['Arquivo anexado']
        return []

    exigidos = list(CAMPOS_OBRIGATORIOS_LIBERACAO.get(
        processo.genero, CAMPOS_OBRIGATORIOS_PADRAO))
    # item 21: a espécie pode exigir valor (não se aplica a Licitações).
    especie = processo.especie_fk if processo.especie_fk_id else None
    if especie is not None and especie.exige_valor:
        exigidos.append(('valor', 'Valor'))
    faltam = []
    for campo, rotulo in exigidos:
        valor = getattr(processo, campo, None)
        vazio = (
            valor in (None, '')
            or (campo == 'status_analise' and valor == 'NAO_APLICAVEL')
        )
        if vazio:
            faltam.append(rotulo)
    return faltam


def analise_completa(processo):
    return not campos_faltantes(processo)


def _exigir_analise_completa(processo, acao):
    faltam = campos_faltantes(processo)
    if not faltam:
        return
    if _eh_licitacao(processo):
        raise TransicaoInvalida(
            f'Anexe ao menos um arquivo antes de {acao}.')
    raise TransicaoInvalida(
        f'Preencha a análise antes de {acao}. '
        f'Faltando: {", ".join(faltam)}.')


# --------------------------------------------------------------------------
# Assumir processo (itens 17 e 39)
# --------------------------------------------------------------------------

@transaction.atomic
def assumir(processo_id, usuario):
    """DISPONIVEL -> EM_ANALISE.

    O responsável pela análise passa a existir só neste momento (item 17).
    A trava impede duas assunções simultâneas (item 39).
    """
    processo = _travar(processo_id)

    perm.assert_permissao(
        perm.pode_assumir_processo(usuario, processo),
        'Somente o analista do grupo pode assumir este processo.')

    if processo.analista_responsavel_id == usuario.id:
        return processo  # idempotente: já é dele

    if processo.situacao_tramite != 'DISPONIVEL':
        if processo.analista_responsavel_id:
            raise TransicaoInvalida(
                f'Processo já está em análise por {processo.nome_analista}.')
        raise TransicaoInvalida(
            f'Processo em "{processo.get_situacao_tramite_display()}" '
            'não pode ser assumido.')

    processo.analista_responsavel = usuario
    processo.data_hora_assumido = timezone.now()
    processo.situacao_tramite = 'EM_ANALISE'
    # Campos legados mantidos em sincronia enquanto as telas antigas existem.
    processo.tecnico = perm.nome_usuario(usuario)
    if not processo.data_analise:
        processo.data_analise = timezone.localdate()
    processo.save()

    registrar_evento(
        processo, 'PROCESSO_ASSUMIDO', usuario,
        descricao=f'Análise assumida por {perm.nome_usuario(usuario)}.')
    registrar_diff(processo, 'situacao_tramite', 'Disponível para análise',
                   f'Em análise por {processo.tecnico}', usuario)
    return processo


# --------------------------------------------------------------------------
# Declinar análise — devolve o processo à fila
# --------------------------------------------------------------------------

CAMPOS_ANALISE_AO_DECLINAR = [
    'analista_responsavel', 'data_hora_assumido', 'tecnico', 'data_analise',
    'numero_despacho', 'numero_relatorio', 'observacao', 'valor', 'periodo',
    'destino', 'destino_fk', 'status_analise', 'situacao_tramite',
]


@transaction.atomic
def declinar_analise(processo_id, usuario, motivo):
    """EM_ANALISE -> DISPONIVEL.

    O analista responsável desiste, ou a Gestão destranca o processo.
    A tentativa de análise é limpa; o histórico do ato permanece.
    """
    processo = _travar(processo_id)

    perm.assert_permissao(
        perm.pode_declinar_analise(usuario, processo),
        'Somente o analista responsável, a Gestão ou o administrador '
        'podem declinar a análise.')

    if processo.situacao_tramite != 'EM_ANALISE':
        raise TransicaoInvalida(
            f'Processo em "{processo.get_situacao_tramite_display()}" '
            'não pode ser devolvido à fila. Só é possível declinar enquanto '
            'estiver em análise.')

    motivo = (motivo or '').strip()
    if not motivo:
        raise TransicaoInvalida('Informe o motivo para devolver o processo à fila.')

    analista_anterior = processo.nome_analista or perm.nome_usuario(
        processo.analista_responsavel)
    numero_relatorio_anterior = processo.numero_relatorio or ''

    processo.analista_responsavel = None
    processo.data_hora_assumido = None
    processo.tecnico = None
    processo.data_analise = None
    processo.numero_despacho = None
    processo.numero_relatorio = None
    processo.observacao = None
    processo.valor = None
    processo.periodo = None
    processo.destino = None
    processo.destino_fk = None
    processo.status_analise = 'NAO_APLICAVEL'
    processo.situacao_tramite = 'DISPONIVEL'
    processo.save(update_fields=CAMPOS_ANALISE_AO_DECLINAR)

    from .relatorios import remover_do_processo
    remover_do_processo(processo)

    motivo_pendencia = f'Análise declinada: {motivo}'
    abertas = list(processo.pendencias.select_for_update().filter(
        status__in=Pendencia.STATUS_ABERTOS))
    agora = timezone.now()
    for pendencia in abertas:
        pendencia.status = 'CANCELADA'
        pendencia.cancelada_em = agora
        pendencia.cancelada_por = usuario
        pendencia.motivo_cancelamento = motivo_pendencia
        pendencia.save(update_fields=[
            'status', 'cancelada_em', 'cancelada_por', 'motivo_cancelamento'])
        registrar_evento_pendencia(pendencia, 'CANCELADA', usuario, motivo_pendencia)

    registrar_evento(
        processo, 'ANALISE_DECLINADA', usuario,
        descricao=(
            f'Análise declinada por {perm.nome_usuario(usuario)}. '
            f'Antes: {analista_anterior or "—"}. Motivo: {motivo}'),
        analista_anterior=analista_anterior,
        motivo=motivo,
        numero_relatorio_anterior=numero_relatorio_anterior,
        pendencias_canceladas=len(abertas),
    )
    registrar_diff(
        processo, 'situacao_tramite',
        f'Em análise por {analista_anterior}',
        'Disponível para análise', usuario)
    return processo


# --------------------------------------------------------------------------
# Administrador: desfazer o último avanço de tramitação
# --------------------------------------------------------------------------

def _ultimo_evento(processo, tipo):
    return (processo.eventos.filter(tipo=tipo)
            .order_by('-criado_em', '-id').first())


@transaction.atomic
def desfazer_tramite(processo_id, usuario, motivo=''):
    """Desfaz o último avanço. Só o administrador.

    EM_ANALISE volta à fila (mesma limpeza de declinar). Os demais estados
    recuam um passo e preservam a análise já gravada.
    """
    perm.assert_permissao(
        perm.pode_desfazer_tramite(usuario),
        'Somente o administrador pode desfazer a tramitação.')

    motivo = (motivo or '').strip() or 'Desfeito pelo administrador'
    atual = Processo.objects.filter(id=processo_id).first()
    if atual is None:
        raise TransicaoInvalida('Processo não encontrado.')
    if atual.esta_cancelado:
        return _desfazer_cancelamento(_travar(processo_id), usuario, motivo)
    if atual.situacao_tramite == 'EM_ANALISE':
        return declinar_analise(processo_id, usuario, motivo)

    processo = _travar(processo_id)
    situacao = processo.situacao_tramite
    if situacao == 'ASSINATURA_DIRECIONADA':
        return _desfazer_direcionamento(processo, usuario, motivo)
    if situacao == 'AGUARDANDO_ASSINATURA':
        return _desfazer_liberacao(processo, usuario, motivo)
    if situacao == 'DISPONIVEL_RETIRADA':
        return _desfazer_retirada(processo, usuario, motivo)
    if situacao == 'SAIDA_CONCLUIDA' or processo.data_saida:
        return _desfazer_saida(processo, usuario, motivo)
    raise TransicaoInvalida(
        f'Processo em "{processo.get_situacao_tramite_display()}" '
        'não tem um passo anterior para desfazer.')


def _registrar_desfazer(processo, usuario, motivo, de, para):
    registrar_evento(
        processo, 'TRAMITE_DESFEITO', usuario,
        descricao=(
            f'Tramitação desfeita por {perm.nome_usuario(usuario)}. '
            f'De "{de}" para "{para}". Motivo: {motivo}'),
        motivo=motivo,
        situacao_anterior=de,
        situacao_nova=para,
    )
    registrar_diff(processo, 'situacao_tramite', de, para, usuario)
    return processo


def _desfazer_direcionamento(processo, usuario, motivo):
    destinatario = processo.nome_assinatura_direcionada or '—'
    processo.assinatura_direcionada_para = None
    processo.assinatura_direcionada_em = None
    processo.situacao_tramite = 'EM_ANALISE'
    processo.save(update_fields=[
        'assinatura_direcionada_para', 'assinatura_direcionada_em',
        'situacao_tramite'])
    return _registrar_desfazer(
        processo, usuario, motivo,
        f'Direcionado para {destinatario}',
        f'Em análise por {processo.nome_analista or "—"}')


def _desfazer_liberacao(processo, usuario, motivo):
    processo.liberado_assinatura_por = None
    processo.liberado_assinatura_em = None
    if processo.assinatura_direcionada_para_id:
        processo.situacao_tramite = 'ASSINATURA_DIRECIONADA'
        para = (f'Direcionado para {processo.nome_assinatura_direcionada}')
    else:
        processo.situacao_tramite = 'EM_ANALISE'
        para = f'Em análise por {processo.nome_analista or "—"}'
    processo.save(update_fields=[
        'liberado_assinatura_por', 'liberado_assinatura_em',
        'situacao_tramite'])
    return _registrar_desfazer(
        processo, usuario, motivo, 'Com o Controlador', para)


def _desfazer_retirada(processo, usuario, motivo):
    processo.disponivel_retirada_em = None
    processo.disponivel_retirada_por = None
    processo.situacao_tramite = 'AGUARDANDO_ASSINATURA'
    processo.save(update_fields=[
        'disponivel_retirada_em', 'disponivel_retirada_por',
        'situacao_tramite'])
    return _registrar_desfazer(
        processo, usuario, motivo,
        'Disponível para retirada', 'Com o Controlador')


def _desfazer_saida(processo, usuario, motivo):
    evento = _ultimo_evento(processo, 'SAIDA_CONCLUIDA')
    dados = (evento.dados or {}) if evento else {}
    anterior = dados.get('situacao_anterior')
    if dados.get('saida_direta') and anterior in Processo.SITUACOES_ATIVAS:
        destino = anterior
        rotulo_para = dict(Processo.SITUACAO_TRAMITE_CHOICES).get(
            destino, destino)
    elif dados.get('legado'):
        destino = 'DISPONIVEL'
        rotulo_para = 'Disponível para análise'
    else:
        destino = 'DISPONIVEL_RETIRADA'
        rotulo_para = 'Disponível para retirada'
    processo.saida_concluida_em = None
    processo.saida_concluida_por = None
    processo.data_saida = None
    processo.hora_saida = None
    processo.situacao_tramite = destino
    processo.save(update_fields=[
        'saida_concluida_em', 'saida_concluida_por',
        'data_saida', 'hora_saida', 'situacao_tramite'])
    return _registrar_desfazer(
        processo, usuario, motivo, 'Saída concluída', rotulo_para)


def _desfazer_cancelamento(processo, usuario, motivo):
    processo.cancelado_em = None
    processo.cancelado_por = None
    processo.motivo_cancelamento = ''
    processo.save(update_fields=[
        'cancelado_em', 'cancelado_por', 'motivo_cancelamento'])
    registrar_evento(
        processo, 'TRAMITE_DESFEITO', usuario,
        descricao=(
            f'Cancelamento desfeito por {perm.nome_usuario(usuario)}. '
            f'Motivo: {motivo}'),
        motivo=motivo)
    return processo


# --------------------------------------------------------------------------
# Direcionar / redirecionar assinatura (itens 8 e 10)
# --------------------------------------------------------------------------

@transaction.atomic
def direcionar_assinatura(processo_id, usuario, destinatario_id):
    """Transfere a análise para outro analista (EM_ANALISE).

    O processo deixa de ser de quem encaminhou e passa a ser do colega:
    ele analisa, devolve à fila ou envia ao Controlador.
    """
    processo = _travar(processo_id)

    perm.assert_permissao(
        perm.pode_direcionar_assinatura(usuario, processo),
        'Somente o analista responsável pode encaminhar a outro analista.')

    if processo.situacao_tramite not in ('EM_ANALISE', 'ASSINATURA_DIRECIONADA'):
        raise TransicaoInvalida(
            f'Processo em "{processo.get_situacao_tramite_display()}" '
            'não permite encaminhar a outro analista.')

    _exigir_analise_completa(processo, 'encaminhar a outro analista')

    try:
        destinatario_id = int(destinatario_id)
    except (TypeError, ValueError):
        raise TransicaoInvalida('Selecione o analista de destino.')
    destinatario = User.objects.filter(id=destinatario_id).first()
    if not perm.is_analista_ativo(destinatario):
        raise TransicaoInvalida('Destinatário deve ser um analista ativo.')
    if destinatario.id == usuario.id:
        raise TransicaoInvalida(
            'Para enviar você mesmo ao Controlador, use "Encaminhar para o Controlador".')

    responsavel_anterior = processo.analista_responsavel
    ja_direcionado = processo.situacao_tramite == 'ASSINATURA_DIRECIONADA'

    processo.analista_responsavel = destinatario
    processo.tecnico = perm.nome_usuario(destinatario)
    processo.data_hora_assumido = timezone.now()
    processo.assinatura_direcionada_para = None
    processo.assinatura_direcionada_em = None
    processo.situacao_tramite = 'EM_ANALISE'
    processo.save(update_fields=[
        'analista_responsavel', 'tecnico', 'data_hora_assumido',
        'assinatura_direcionada_para', 'assinatura_direcionada_em',
        'situacao_tramite'])

    Pendencia.objects.filter(
        processo=processo, status__in=Pendencia.STATUS_ABERTOS
    ).update(responsavel_tecnico=destinatario)

    if processo.numero_relatorio:
        from .relatorios import registrar as registrar_relatorio
        registrar_relatorio(processo)

    registrar_evento(
        processo,
        'ASSINATURA_REDIRECIONADA' if ja_direcionado else 'ASSINATURA_DIRECIONADA',
        usuario,
        descricao=(
            f'Análise encaminhada para {perm.nome_usuario(destinatario)}. '
            f'O processo passou a ser dele.'),
        analista_anterior=perm.nome_usuario(responsavel_anterior),
        destinatario=perm.nome_usuario(destinatario),
    )
    registrar_diff(
        processo, 'tecnico',
        perm.nome_usuario(responsavel_anterior),
        perm.nome_usuario(destinatario), usuario)
    return processo


# --------------------------------------------------------------------------
# Liberar para assinatura (item 11)
# --------------------------------------------------------------------------

@transaction.atomic
def liberar_assinatura(processo_id, usuario):
    """EM_ANALISE ou ASSINATURA_DIRECIONADA -> AGUARDANDO_ASSINATURA.

    Fluxo normal: executa o analista responsável.
    Fluxo direcionado: executa o analista para quem foi direcionado.

    `analista_responsavel` NÃO é alterado: quem analisou continua sendo
    quem analisou (item 7).
    """
    processo = _travar(processo_id)

    perm.assert_permissao(
        perm.pode_liberar_assinatura(usuario, processo),
        'Somente o analista responsável ou o destinatário do '
        'direcionamento pode liberar para assinatura.')

    if processo.situacao_tramite not in ('EM_ANALISE', 'ASSINATURA_DIRECIONADA'):
        raise TransicaoInvalida(
            f'Processo em "{processo.get_situacao_tramite_display()}" '
            'não pode ser liberado para assinatura.')

    if (processo.situacao_tramite == 'ASSINATURA_DIRECIONADA'
            and usuario.id != processo.assinatura_direcionada_para_id):
        raise TransicaoInvalida(
            'A assinatura foi direcionada para '
            f'{processo.nome_assinatura_direcionada}.')

    _exigir_analise_completa(processo, 'liberar para assinatura')

    from .relatorios import atribuir_se_preciso
    atribuir_se_preciso(processo)

    processo.situacao_tramite = 'AGUARDANDO_ASSINATURA'
    processo.liberado_assinatura_por = usuario
    processo.liberado_assinatura_em = timezone.now()
    processo.save(update_fields=['situacao_tramite',
                                 'liberado_assinatura_por',
                                 'liberado_assinatura_em',
                                 'numero_relatorio'])

    substitutiva = usuario.id != processo.analista_responsavel_id
    registrar_evento(
        processo, 'LIBERADO_ASSINATURA', usuario,
        descricao=('Liberado para assinatura por '
                   f'{perm.nome_usuario(usuario)}'
                   + (' (assinatura substitutiva).' if substitutiva else '.')),
        analista_da_analise=processo.nome_analista,
        assinatura_substitutiva=substitutiva,
    )
    return processo


# --------------------------------------------------------------------------
# Protocolo: retorno físico do processo assinado (item 13)
# --------------------------------------------------------------------------

@transaction.atomic
def disponibilizar_retirada(processo_id, usuario):
    """AGUARDANDO_ASSINATURA -> DISPONIVEL_RETIRADA.

    Executado pelo Protocolo quando o processo volta fisicamente já
    assinado pelo Controlador.
    """
    processo = _travar(processo_id)

    perm.assert_permissao(
        perm.pode_disponibilizar_retirada(usuario),
        'Somente o Protocolo pode disponibilizar para retirada.')

    if processo.situacao_tramite != 'AGUARDANDO_ASSINATURA':
        raise TransicaoInvalida(
            f'Processo em "{processo.get_situacao_tramite_display()}" '
            'não está liberado para assinatura.')

    processo.situacao_tramite = 'DISPONIVEL_RETIRADA'
    processo.disponivel_retirada_em = timezone.now()
    processo.disponivel_retirada_por = usuario
    processo.save(update_fields=['situacao_tramite',
                                 'disponivel_retirada_em',
                                 'disponivel_retirada_por'])

    registrar_evento(
        processo, 'DISPONIVEL_RETIRADA', usuario,
        descricao='Processo assinado retornou ao Protocolo e está '
                  'disponível para retirada.')
    return processo


# --------------------------------------------------------------------------
# Saída em lote (itens 14 e 15)
# --------------------------------------------------------------------------

@transaction.atomic
def registrar_saida(ids, usuario):
    """DISPONIVEL_RETIRADA -> SAIDA_CONCLUIDA, em lote.

    Tudo ou nada: se um único processo estiver em situação inválida, a
    operação inteira é abortada (item 15).
    """
    perm.assert_permissao(
        perm.pode_registrar_saida(usuario),
        'Somente o Protocolo ou o administrador pode registrar saída.')

    ids = [int(i) for i in ids if str(i).strip()]
    if not ids:
        raise TransicaoInvalida('Nenhum processo selecionado.')

    # 1. bloquear todos os registros
    processos = list(Processo.objects.select_for_update()
                     .filter(id__in=ids).order_by('id'))

    # 2. validar todos antes de alterar qualquer um
    encontrados = {p.id for p in processos}
    faltando = set(ids) - encontrados
    if faltando:
        raise TransicaoInvalida(
            f'Processo(s) não encontrado(s): {sorted(faltando)}.')

    invalidos = [p for p in processos
                 if p.situacao_tramite != 'DISPONIVEL_RETIRADA'
                 or p.esta_cancelado]
    if invalidos:
        lista = ', '.join(
            f'{p.numero_processo} ({p.get_situacao_tramite_display()})'
            for p in invalidos)
        raise TransicaoInvalida(
            f'Operação cancelada. Não estão disponíveis para retirada: {lista}.')

    # 3. só então atualizar
    agora = timezone.now()
    local = timezone.localtime(agora)
    for processo in processos:
        processo.situacao_tramite = 'SAIDA_CONCLUIDA'
        processo.saida_concluida_em = agora
        processo.saida_concluida_por = usuario
        # Campos legados: as telas de finalizados ainda leem data_saida.
        processo.data_saida = local.date()
        processo.hora_saida = local.time().replace(microsecond=0)
        processo.save(update_fields=['situacao_tramite', 'saida_concluida_em',
                                     'saida_concluida_por', 'data_saida',
                                     'hora_saida'])
        # Item 15: cada processo recebe seu próprio evento.
        registrar_evento(
            processo, 'SAIDA_CONCLUIDA', usuario,
            descricao=f'Saída registrada por {perm.nome_usuario(usuario)}.',
            destino=processo.destino,
            total_no_lote=len(processos),
        )
    return processos


# --------------------------------------------------------------------------
# Alteração excepcional do destino (item 16)
# --------------------------------------------------------------------------

@transaction.atomic
def alterar_destino(processo_id, usuario, novo_destino,
                    autorizado_por, observacao=''):
    """Ação específica do Protocolo. Não é edição livre do campo."""
    processo = _travar(processo_id)

    perm.assert_permissao(
        perm.pode_alterar_destino(usuario),
        'Somente o Protocolo pode alterar o destino.')

    novo_destino = (novo_destino or '').strip()
    autorizado_por = (autorizado_por or '').strip()
    if not novo_destino:
        raise TransicaoInvalida('Novo destino é obrigatório.')
    if not autorizado_por:
        raise TransicaoInvalida('É obrigatório informar quem autorizou.')
    if processo.situacao_tramite == 'SAIDA_CONCLUIDA':
        raise TransicaoInvalida(
            'Processo com saída concluída não permite alteração de destino '
            'pelo fluxo normal.')

    anterior = processo.destino or ''
    if anterior.strip() == novo_destino:
        return processo

    processo.destino = novo_destino
    # item 20: quando o destino é unidade municipal cadastrada, liga a FK.
    from .cadastros import resolver_unidade
    processo.destino_fk = resolver_unidade(novo_destino)
    processo.save(update_fields=['destino', 'destino_fk'])

    registrar_evento(
        processo, 'DESTINO_ALTERADO', usuario,
        descricao=f'Destino alterado de "{anterior}" para "{novo_destino}".',
        destino_anterior=anterior,
        destino_novo=novo_destino,
        autorizado_por=autorizado_por,
        observacao=observacao or '',
    )
    registrar_diff(processo, 'destino', anterior, novo_destino, usuario)
    return processo


# --------------------------------------------------------------------------
# Prioridade (item 17) e cancelamento (item 35) — Gestão
# --------------------------------------------------------------------------

def escolher_recorrencia(valor):
    """'sim' / 'nao' vindos do balão. Outro valor não altera a preferência."""
    return {'sim': True, 'nao': False}.get(valor)


def mensagem_de_prioridade(processo, escolha):
    texto = (f'Prioridade de {processo.numero_processo} atualizada para '
             f'{processo.get_prioridade_display()}.')
    if processo.prioridade != 'URGENTE':
        return texto
    if escolha == 'sim':
        return texto + ' As próximas entradas deste número já nascem urgentes.'
    if escolha == 'nao':
        return texto + ' Vale só nesta entrada.'
    return texto


@transaction.atomic
def alterar_prioridade(processo_id, usuario, prioridade, recorrente=None):
    processo = _travar(processo_id)

    perm.assert_permissao(
        perm.pode_alterar_prioridade(usuario),
        'Somente a Gestão altera a prioridade.')

    # item 22: a prioridade válida é a do cadastro (ativa).
    from .cadastros import resolver_prioridade
    cadastro = resolver_prioridade(prioridade)
    if cadastro is None or not cadastro.ativo:
        raise TransicaoInvalida('Prioridade inválida ou inativa.')
    prioridade = cadastro.codigo

    anterior = processo.prioridade
    if anterior == prioridade:
        return processo

    processo.prioridade = prioridade
    processo.prioridade_fk = cadastro
    processo.prazo_dias = cadastro.prazo_dias
    processo.save(update_fields=['prioridade', 'prioridade_fk', 'prazo_dias'])

    if prioridade == 'URGENTE' and recorrente is not None:
        UrgenciaRecorrente.definir(processo.numero_processo, bool(recorrente), usuario)

    descricao = f'Prioridade alterada para {processo.get_prioridade_display()}.'
    if prioridade == 'URGENTE' and recorrente is True:
        descricao += ' As próximas entradas deste número já nascem urgentes.'
    elif prioridade == 'URGENTE' and recorrente is False:
        descricao += ' Vale só nesta entrada.'

    registrar_evento(
        processo, 'PRIORIDADE_ALTERADA', usuario,
        descricao=descricao,
        prioridade_anterior=anterior,
        prioridade_nova=prioridade,
    )
    registrar_diff(processo, 'prioridade', anterior, prioridade, usuario)
    return processo


@transaction.atomic
def cancelar_processo(processo_id, usuario, motivo):
    """Substitui a exclusão destrutiva (item 35). O registro permanece."""
    processo = _travar(processo_id)

    perm.assert_permissao(
        perm.pode_cancelar_processo(usuario),
        'Somente a Gestão pode cancelar processo.')

    motivo = (motivo or '').strip()
    if not motivo:
        raise TransicaoInvalida('Motivo do cancelamento é obrigatório.')
    if processo.esta_cancelado:
        raise TransicaoInvalida('Processo já está cancelado.')

    processo.cancelado_em = timezone.now()
    processo.cancelado_por = usuario
    processo.motivo_cancelamento = motivo
    processo.save(update_fields=['cancelado_em', 'cancelado_por',
                                 'motivo_cancelamento'])

    registrar_evento(
        processo, 'PROCESSO_CANCELADO', usuario,
        descricao=f'Processo cancelado. Motivo: {motivo}',
        situacao_no_cancelamento=processo.situacao_tramite)
    return processo


# --------------------------------------------------------------------------
# Consultas de apoio
# --------------------------------------------------------------------------

def disponiveis_para_retirada(usuario=None):
    """item 14: bloco 'Processos disponíveis para retirada — N'."""
    return (Processo.objects
            .filter(situacao_tramite='DISPONIVEL_RETIRADA',
                    cancelado_em__isnull=True)
            .order_by('disponivel_retirada_em', 'numero_processo'))


def liberados_para_assinatura():
    """item 12: o que a Gestão precisa coletar para assinatura física."""
    return (Processo.objects
            .filter(situacao_tramite='AGUARDANDO_ASSINATURA',
                    cancelado_em__isnull=True)
            .select_related('analista_responsavel', 'liberado_assinatura_por')
            .order_by('liberado_assinatura_em'))


def ativos():
    """item 58: ativo é o que não saiu e não foi cancelado.

    `data_saida__isnull` entra por compatibilidade: registros anteriores à
    nova tramitação têm a saída gravada só em data_saida. Depois de rodar
    `python manage.py sanear_dados --aplicar`, os dois critérios coincidem.
    """
    return Processo.objects.filter(
        situacao_tramite__in=Processo.SITUACOES_ATIVAS,
        data_saida__isnull=True,
        cancelado_em__isnull=True)


def finalizados():
    """item 58: finalizado fisicamente = SAIDA_CONCLUIDA (ou saída legada)."""
    from django.db.models import Q
    return Processo.objects.filter(
        Q(situacao_tramite='SAIDA_CONCLUIDA') | Q(data_saida__isnull=False),
        cancelado_em__isnull=True)


# --------------------------------------------------------------------------
# Transição: processos anteriores à nova tramitação
# --------------------------------------------------------------------------

def eh_legado(processo):
    """Processo que entrou antes da nova tramitação e nunca passou por ela.

    Critério derivado, sem campo novo: não tem evento PROCESSO_CADASTRADO
    (todo processo criado pelo fluxo novo tem) e continua em DISPONIVEL,
    sem analista. É o acervo que estava em andamento quando o sistema só
    registrava o Protocolo.
    """
    if not (processo.situacao_tramite == 'DISPONIVEL'
            and processo.analista_responsavel_id is None
            and processo.data_saida is None):
        return False
    # As listas anotam `tem_evento_cadastro` para não consultar linha a linha.
    tem_evento = getattr(processo, 'tem_evento_cadastro', None)
    if tem_evento is None:
        tem_evento = processo.eventos.filter(tipo='PROCESSO_CADASTRADO').exists()
    return not tem_evento


def pode_saida_direta(processo):
    """O Protocolo pode dar saída neste processo agora, sem as etapas do meio."""
    return (
        not processo.esta_cancelado
        and processo.data_saida is None
        and processo.situacao_tramite in Processo.SITUACOES_ATIVAS
    )


def _gravar_saida(processo, usuario, descricao, dados_evento):
    agora = timezone.now()
    local = timezone.localtime(agora)
    processo.situacao_tramite = 'SAIDA_CONCLUIDA'
    processo.saida_concluida_em = agora
    processo.saida_concluida_por = usuario
    processo.data_saida = local.date()
    processo.hora_saida = local.time().replace(microsecond=0)
    processo.save(update_fields=['situacao_tramite', 'saida_concluida_em',
                                 'saida_concluida_por', 'data_saida', 'hora_saida'])
    registrar_evento(processo, 'SAIDA_CONCLUIDA', usuario,
                     descricao=descricao, **dados_evento)
    registrar_diff(processo, 'data_saida', '',
                   processo.data_saida.strftime('%Y-%m-%d'), usuario)
    return processo


@transaction.atomic
def registrar_saida_direta(processo_id, usuario):
    """Saída pelo Protocolo de qualquer processo ainda na CGM.

    A tramitação completa (assumir, encaminhar, disponibilizar) continua
    existindo. Esta via existe para a casa conseguir registrar entrada e
    saída sem estar organizada nas etapas do meio.
    """
    processo = _travar(processo_id)
    perm.assert_permissao(perm.pode_registrar_saida(usuario),
                          'Somente o Protocolo ou o administrador pode registrar saída.')
    if processo.esta_cancelado:
        raise TransicaoInvalida('Processo cancelado não recebe saída.')
    if not pode_saida_direta(processo):
        raise TransicaoInvalida(
            'Este processo já saiu ou não está mais na CGM.')

    situacao_anterior = processo.get_situacao_tramite_display()
    codigo_anterior = processo.situacao_tramite
    legado = eh_legado(processo)
    if legado:
        descricao = ('Saída registrada pelo Protocolo (processo anterior à '
                     'nova tramitação).')
        dados = {'legado': True, 'destino': processo.destino}
    elif codigo_anterior == 'DISPONIVEL_RETIRADA':
        descricao = f'Saída registrada por {perm.nome_usuario(usuario)}.'
        dados = {'destino': processo.destino}
    else:
        descricao = (
            f'Saída registrada pelo Protocolo, sem passar pelas etapas de '
            f'análise. Situação anterior: {situacao_anterior}.'
        )
        dados = {
            'saida_direta': True,
            'situacao_anterior': codigo_anterior,
            'destino': processo.destino,
        }
    return _gravar_saida(processo, usuario, descricao, dados)


@transaction.atomic
def registrar_saida_legado(processo_id, usuario):
    """Compatível com o acervo antigo; usa a saída direta do Protocolo."""
    return registrar_saida_direta(processo_id, usuario)


# --------------------------------------------------------------------------
# Internos
# --------------------------------------------------------------------------

def _travar(processo_id):
    """Carrega o processo com trava de linha. Sempre dentro de atomic()."""
    processo = (Processo.objects.select_for_update()
                .filter(id=processo_id).first())
    if processo is None:
        raise TransicaoInvalida('Processo não encontrado.')
    return processo
