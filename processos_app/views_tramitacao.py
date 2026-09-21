# processos_app/views_tramitacao.py
"""
Endpoints específicos das transições de estado (item 52).

Cada operação tem seu próprio endpoint. Nenhuma delas passa por
`atualizar_processo`, que é o endpoint genérico de edição.

As views aqui só tratam HTTP: lêem o POST, chamam o service e devolvem
mensagem. Quem decide é `services/tramitacao.py`.

Sem @csrf_exempt (item 53): todo formulário deve trazer {% csrf_token %}.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import Processo
from .services import permissions as perm
from .services import prazos, tramitacao


def _mensagem_de_erro(exc):
    """Mensagem limpa, sem expor exceção interna (item 53)."""
    if isinstance(exc, ValidationError):
        return '; '.join(exc.messages)
    return str(exc)


def _executar(request, funcao, destino, *args, sucesso='', **kwargs):
    """Chama o service e converte exceções em mensagens."""
    try:
        resultado = funcao(*args, **kwargs)
    except PermissionDenied as exc:
        messages.error(request, _mensagem_de_erro(exc))
        return redirect(destino), None
    except ValidationError as exc:
        messages.error(request, _mensagem_de_erro(exc))
        return redirect(destino), None
    if sucesso:
        messages.success(request, sucesso)
    return None, resultado


# --------------------------------------------------------------------------
# Analista
# --------------------------------------------------------------------------

@login_required
@require_POST
def assumir(request, process_id):
    """item 39: assumir com trava de concorrência."""
    erro, processo = _executar(
        request, tramitacao.assumir, 'area_analista',
        process_id, request.user,
        sucesso='Processo assumido. A análise ficou registrada em seu nome.')
    if erro:
        return erro
    return redirect('analista_processo', process_id=processo.id)


@login_required
@require_POST
def declinar_analise(request, process_id):
    """Devolve o processo à fila como disponível."""
    destino = 'gestao_processos' if perm.is_gestao(request.user) else 'area_analista'
    erro, _ = _executar(
        request, tramitacao.declinar_analise, destino,
        process_id, request.user, request.POST.get('motivo'),
        sucesso='Processo devolvido à fila, sem análise.')
    return erro or redirect(destino)


@login_required
@require_POST
def direcionar_assinatura(request, process_id):
    """itens 8 e 10: direcionar e redirecionar a assinatura."""
    erro, processo = _executar(
        request, tramitacao.direcionar_assinatura, 'area_analista',
        process_id, request.user, request.POST.get('destinatario'),
        sucesso='Processo encaminhado para outro analista.')
    if erro:
        return erro
    return redirect('analista_processo', process_id=processo.id)


@login_required
@require_POST
def liberar_assinatura(request, process_id):
    """item 11."""
    erro, _ = _executar(
        request, tramitacao.liberar_assinatura, 'area_analista',
        process_id, request.user,
        sucesso='Processo encaminhado para o Controlador.')
    return erro or redirect('area_analista')


# --------------------------------------------------------------------------
# Protocolo
# --------------------------------------------------------------------------

@login_required
@require_POST
def disponibilizar_retirada(request, process_id):
    """item 13: o processo assinado voltou fisicamente ao Protocolo."""
    erro, _ = _executar(
        request, tramitacao.disponibilizar_retirada, 'processos_para_retirada',
        process_id, request.user,
        sucesso='Processo disponibilizado para retirada.')
    return erro or redirect('processos_para_retirada')


@login_required
@perm.exige(perm.is_protocolo, 'Área exclusiva do Protocolo.')
def processos_para_retirada(request):
    """item 14: tela "Processos disponíveis para retirada — N"."""
    disponiveis = tramitacao.disponiveis_para_retirada()
    aguardando = tramitacao.liberados_para_assinatura()
    return render(request, 'protocolo/retirada.html', {
        'disponiveis': disponiveis,
        'total_disponiveis': disponiveis.count(),
        'aguardando_assinatura': aguardando,
        'total_aguardando': aguardando.count(),
        **perm.contexto_de_permissoes(request.user),
    })


@login_required
@require_POST
def registrar_saida(request, process_id=None):
    """item 15: saída em lote, tudo ou nada.

    Aceita tanto a seleção múltipla (`processos`) quanto um único id na URL.
    """
    ids = request.POST.getlist('processos') or ([process_id] if process_id else [])
    erro, processos = _executar(
        request, tramitacao.registrar_saida, 'processos_para_retirada',
        ids, request.user)
    if erro:
        return erro
    n = len(processos)
    messages.success(
        request,
        f'Saída registrada para {n} processo' + ('s.' if n > 1 else '.'))
    return redirect('processos_para_retirada')


@login_required
@require_POST
def alterar_destino(request, process_id):
    """item 16: ação específica, não edição livre do campo."""
    erro, _ = _executar(
        request, tramitacao.alterar_destino, 'listar_processos',
        process_id, request.user,
        request.POST.get('novo_destino'),
        request.POST.get('autorizado_por'),
        request.POST.get('observacao', ''),
        sucesso='Destino alterado e registrado no histórico.')
    return erro or redirect(request.POST.get('next') or 'listar_processos')


@login_required
def form_alterar_destino(request, process_id):
    """Tela da alteração excepcional de destino.

    Destino atual em somente leitura; novo destino e "autorizado por"
    obrigatórios; usuário, data e hora automáticos (item 16).
    """
    perm.assert_permissao(perm.pode_alterar_destino(request.user),
                          'Somente o Protocolo pode alterar o destino.')
    processo = get_object_or_404(Processo, id=process_id)
    return render(request, 'protocolo/alterar_destino.html', {
        'processo': processo,
        'bloqueado': processo.situacao_tramite == 'SAIDA_CONCLUIDA',
    })


# --------------------------------------------------------------------------
# Gestão
# --------------------------------------------------------------------------

@login_required
@require_POST
def alterar_prioridade(request, process_id):
    """item 17: a prioridade é gerenciada pela Gestão."""
    erro, processo = _executar(
        request, tramitacao.alterar_prioridade, 'gestao_processos',
        process_id, request.user, request.POST.get('prioridade'))
    if erro:
        return erro
    messages.success(
        request,
        f'Prioridade de {processo.numero_processo} atualizada para '
        f'{processo.get_prioridade_display()}.')
    return redirect('gestao_processos')


@login_required
@require_POST
def cancelar_processo(request, process_id):
    """item 35: cancelamento lógico substitui a exclusão."""
    erro, _ = _executar(
        request, tramitacao.cancelar_processo, 'gestao_processos',
        process_id, request.user, request.POST.get('motivo'),
        sucesso='Processo cancelado. O registro foi preservado.')
    return erro or redirect('gestao_processos')


@login_required
@perm.exige(perm.is_gestao, 'Área exclusiva da Gestão.')
def liberados_para_assinatura(request):
    """item 12: o que a Gestão precisa coletar para assinatura física.

    Sem "Confirmar assinatura", sem "Assinado", sem "Encaminhar ao
    Protocolo" — essas etapas não são registradas no sistema.
    """
    processos = tramitacao.liberados_para_assinatura()
    return render(request, 'gestao/liberados_assinatura.html', {
        'processos': processos,
        'total': processos.count(),
        **perm.contexto_de_permissoes(request.user),
    })


# --------------------------------------------------------------------------
# Apoio ao direcionamento (itens 9 e 24)
# --------------------------------------------------------------------------

def opcoes_de_analistas(usuario_atual=None):
    """Lista para o seletor de direcionamento (itens 8, 9 e 24).

    Mostra a disponibilidade vinda da Gestão de Pessoas CGM — "Allan —
    Disponível", "Natália — Curso hoje". É informação: nenhuma opção é
    desabilitada (item 9). Não filtra por grupo (item 8).
    """
    from .services import gestao_pessoas

    analistas = [a for a in perm.analistas_ativos()
                 if not (usuario_atual and a.id == usuario_atual.id)]
    disponibilidade = gestao_pessoas.mapa_disponibilidade(analistas)
    return [{
        'id': analista.id,
        'nome': perm.nome_usuario(analista),
        'grupo': perm.grupo_do_analista(analista),
        'disponibilidade': disponibilidade.get(analista.id, gestao_pessoas.DISPONIVEL),
        'disponivel': disponibilidade.get(analista.id) == gestao_pessoas.DISPONIVEL,
    } for analista in analistas]
