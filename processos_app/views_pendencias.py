# processos_app/views_pendencias.py
"""
Telas e endpoints de Pendências e Diligências (itens 28, 29, 30, 32, 34).

Views só tratam HTTP. As regras estão em services/pendencias.py.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from .models import Pendencia
from .services import pendencias as svc
from .services import permissions as perm


def _erro(request, exc):
    messages.error(request, '; '.join(getattr(exc, 'messages', [str(exc)])))


def _voltar_para_processo(pendencia_id):
    pendencia = Pendencia.objects.filter(id=pendencia_id).first()
    if pendencia:
        return redirect('analista_processo', process_id=pendencia.processo_id)
    return redirect('area_analista')


# --------------------------------------------------------------------------
# Gestão — Diligências (itens 28 e 29)
# --------------------------------------------------------------------------

@login_required
@perm.exige(perm.is_gestao, 'Área exclusiva da Gestão.')
def diligencias(request):
    """Lista prioritariamente as pendências em AGUARDANDO_ATENDIMENTO.

    Exibe só o que o documento pede: processo, Secretaria, descrição,
    analista responsável, tempo decorrido e a ação.

    Não há botão para registrar telefonema, e-mail ou cobrança: esses atos
    são operacionais e não entram no sistema (item 25).
    """
    status = request.GET.get('status', 'AGUARDANDO_ATENDIMENTO')
    if status not in dict(Pendencia.STATUS_CHOICES) and status != 'ABERTAS':
        status = 'AGUARDANDO_ATENDIMENTO'

    lista = svc.fila_diligencias(status)
    return render(request, 'gestao/diligencias.html', {
        'pendencias': lista,
        'total': lista.count(),
        'status_atual': status,
        'status_choices': Pendencia.STATUS_CHOICES,
        'total_aguardando': svc.fila_diligencias(
            'AGUARDANDO_ATENDIMENTO').count(),
        'total_indicados': svc.fila_diligencias(
            'ATENDIMENTO_INDICADO').count(),
        **perm.contexto_de_permissoes(request.user),
    })


@login_required
@require_POST
def indicar_atendimento(request, pendencia_id):
    """item 29: apenas a Gestão."""
    try:
        svc.indicar_atendimento(pendencia_id, request.user)
        messages.success(
            request,
            'Atendimento indicado. A pendência foi para o analista avaliar.')
    except (PermissionDenied, ValidationError) as exc:
        _erro(request, exc)
    return redirect('gestao_diligencias')


# --------------------------------------------------------------------------
# Analista — atendimentos indicados (item 30)
# --------------------------------------------------------------------------

@login_required
@perm.exige(perm.is_analista, 'Área exclusiva dos analistas.')
def meus_atendimentos(request):
    """Tela "Atendimentos indicados — N"."""
    lista = svc.atendimentos_indicados(request.user)
    return render(request, 'analista/atendimentos.html', {
        'pendencias': lista,
        'total': lista.count(),
        **perm.contexto_de_permissoes(request.user),
    })


@login_required
@require_POST
def confirmar_resolucao(request, pendencia_id):
    """Não exige texto adicional (item 30)."""
    destino = request.POST.get('next')
    try:
        svc.confirmar_resolucao(pendencia_id, request.user)
        messages.success(request, 'Pendência resolvida.')
    except (PermissionDenied, ValidationError) as exc:
        _erro(request, exc)
    return redirect(destino) if destino else _voltar_para_processo(pendencia_id)


@login_required
@require_POST
def atendimento_insuficiente(request, pendencia_id):
    """Exige apenas "O que ainda precisa ser atendido?" (item 30)."""
    destino = request.POST.get('next')
    try:
        svc.atendimento_insuficiente(
            pendencia_id, request.user, request.POST.get('o_que_falta'))
        messages.success(
            request,
            'Pendência devolvida. Ela reapareceu na fila de Diligências.')
    except (PermissionDenied, ValidationError) as exc:
        _erro(request, exc)
    return redirect(destino) if destino else _voltar_para_processo(pendencia_id)


@login_required
@require_POST
def cancelar_pendencia(request, pendencia_id):
    """item 32: cancelar exige motivo; a pendência não é apagada."""
    destino = request.POST.get('next')
    try:
        svc.cancelar(pendencia_id, request.user, request.POST.get('motivo'))
        messages.success(request, 'Pendência cancelada.')
    except (PermissionDenied, ValidationError) as exc:
        _erro(request, exc)
    return redirect(destino) if destino else _voltar_para_processo(pendencia_id)
