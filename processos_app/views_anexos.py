"""Upload, preview e download dos arquivos do processo de Licitações."""

import mimetypes

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_POST

from .models import AnexoProcesso, Processo
from .services import anexos as svc
from .services import permissions as perm


def _abrir_anexo(anexo, usuario, *, inline=False):
    perm.assert_permissao(
        perm.pode_ver_grupo(usuario, anexo.processo.grupo),
        'Você não tem permissão para ver este arquivo.')
    if not anexo.arquivo:
        raise Http404('Arquivo não encontrado.')
    try:
        handle = anexo.arquivo.open('rb')
    except FileNotFoundError as exc:
        raise Http404('Arquivo não encontrado.') from exc
    content_type, _ = mimetypes.guess_type(anexo.nome_original or '')
    return FileResponse(
        handle,
        as_attachment=not inline,
        filename=anexo.nome_original,
        content_type=content_type or 'application/octet-stream',
    )


def _voltar_processo(processo_id):
    return redirect(
        reverse('analista_processo', args=[processo_id]) + '#blocoAnexos')


@login_required
@require_POST
def anexar_arquivo(request, process_id):
    processo = get_object_or_404(Processo, id=process_id)
    try:
        salvos, erros = svc.anexar(
            processo, request.user, request.FILES.getlist('arquivos'))
    except (PermissionDenied, ValidationError) as exc:
        messages.error(request, '; '.join(getattr(exc, 'messages', [str(exc)])))
        return _voltar_processo(processo.id)

    if salvos:
        if len(salvos) == 1:
            messages.success(request, '1 arquivo anexado.')
        else:
            messages.success(request, f'{len(salvos)} arquivos anexados.')
    for erro in erros:
        messages.error(request, erro)
    return _voltar_processo(processo.id)


@login_required
@require_POST
def remover_anexo(request, anexo_id):
    anexo = get_object_or_404(AnexoProcesso, id=anexo_id)
    processo_id = anexo.processo_id
    try:
        svc.remover(anexo.id, request.user)
    except (PermissionDenied, ValidationError, AnexoProcesso.DoesNotExist) as exc:
        messages.error(request, '; '.join(getattr(exc, 'messages', [str(exc)])))
        return _voltar_processo(processo_id)
    messages.success(request, 'Arquivo removido.')
    return _voltar_processo(processo_id)


@login_required
def baixar_anexo(request, anexo_id):
    anexo = get_object_or_404(
        AnexoProcesso.objects.select_related('processo'), id=anexo_id)
    return _abrir_anexo(anexo, request.user, inline=False)


@login_required
@xframe_options_sameorigin
def ver_anexo(request, anexo_id):
    """Abre o arquivo no navegador/iframe (preview), inclusive após a análise."""
    anexo = get_object_or_404(
        AnexoProcesso.objects.select_related('processo'), id=anexo_id)
    return _abrir_anexo(anexo, request.user, inline=True)
