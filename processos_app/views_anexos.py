"""Upload e download dos arquivos do processo de Licitações e Contratos."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from .models import AnexoProcesso, Processo
from .services import anexos as svc
from .services import permissions as perm


@login_required
@require_POST
def anexar_arquivo(request, process_id):
    processo = get_object_or_404(Processo, id=process_id)
    try:
        salvos, erros = svc.anexar(
            processo, request.user, request.FILES.getlist('arquivos'))
    except (PermissionDenied, ValidationError) as exc:
        messages.error(request, '; '.join(getattr(exc, 'messages', [str(exc)])))
        return redirect('analista_processo', process_id=processo.id)

    if salvos:
        if len(salvos) == 1:
            messages.success(request, '1 arquivo anexado.')
        else:
            messages.success(request, f'{len(salvos)} arquivos anexados.')
    for erro in erros:
        messages.error(request, erro)
    return redirect('analista_processo', process_id=processo.id)


@login_required
@require_POST
def remover_anexo(request, anexo_id):
    anexo = get_object_or_404(AnexoProcesso, id=anexo_id)
    processo_id = anexo.processo_id
    try:
        svc.remover(anexo.id, request.user)
    except (PermissionDenied, ValidationError, AnexoProcesso.DoesNotExist) as exc:
        messages.error(request, '; '.join(getattr(exc, 'messages', [str(exc)])))
        return redirect('analista_processo', process_id=processo_id)
    messages.success(request, 'Arquivo removido.')
    return redirect('analista_processo', process_id=processo_id)


@login_required
def baixar_anexo(request, anexo_id):
    anexo = get_object_or_404(
        AnexoProcesso.objects.select_related('processo'), id=anexo_id)
    perm.assert_permissao(
        perm.pode_ver_grupo(request.user, anexo.processo.grupo),
        'Você não tem permissão para ver este arquivo.')
    if not anexo.arquivo:
        raise Http404('Arquivo não encontrado.')
    try:
        handle = anexo.arquivo.open('rb')
    except FileNotFoundError as exc:
        raise Http404('Arquivo não encontrado.') from exc
    return FileResponse(handle, as_attachment=True, filename=anexo.nome_original)
