"""Upload, preview e download dos arquivos do processo de Licitações."""

import mimetypes

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_POST

from .models import AnexoProcesso, Processo
from .services import anexos as svc
from .services import permissions as perm


def _quer_json(request):
    accept = (request.headers.get('Accept') or '').lower()
    return (
        request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        or 'application/json' in accept
    )


def _pagina_preview_indisponivel(anexo, motivo):
    """HTML no iframe — evita o navegador embutir .docx e falhar no domínio."""
    from django.utils.html import escape

    nome = escape(anexo.nome_original or 'Arquivo')
    motivo = escape(motivo)
    baixar = reverse('baixar_anexo', args=[anexo.id])
    return HttpResponse(
        '<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8">'
        f'<title>{nome}</title>'
        '<style>'
        'body{font-family:Segoe UI,Arial,sans-serif;margin:24px;color:#0f172a;'
        'background:#f8fafc;}'
        '.box{max-width:420px;margin:40px auto;padding:24px;background:#fff;'
        'border:1px solid #e2e8f0;border-radius:12px;text-align:center;}'
        'p{color:#64748b;line-height:1.5;}'
        'a{display:inline-flex;align-items:center;gap:6px;margin-top:12px;'
        'padding:10px 16px;border-radius:8px;background:#1d4ed8;color:#fff;'
        'text-decoration:none;font-weight:600;}'
        '</style></head><body><div class="box">'
        f'<strong>{nome}</strong>'
        f'<p>{motivo}</p>'
        f'<a href="{baixar}" target="_parent">Baixar arquivo</a>'
        '</div></body></html>',
        content_type='text/html; charset=utf-8',
    )


def _abrir_anexo(anexo, usuario, *, inline=False):
    perm.assert_permissao(
        perm.pode_ver_grupo(usuario, anexo.processo.grupo),
        'Você não tem permissão para ver este arquivo.')
    if not anexo.arquivo:
        if inline:
            return _pagina_preview_indisponivel(
                anexo, 'Arquivo não encontrado no servidor.')
        raise Http404('Arquivo não encontrado.')

    # Preview Word (.docx): só HTML no iframe. Nunca embute o binário —
    # o navegador tenta abrir via o host e pode falhar (conexão recusada).
    if inline and anexo.extensao == '.docx':
        html = svc.html_preview_docx(anexo)
        if html:
            return HttpResponse(html, content_type='text/html; charset=utf-8')
        return _pagina_preview_indisponivel(
            anexo,
            'Não foi possível gerar a pré-visualização deste Word. '
            'Baixe o arquivo para abrir no computador.')

    if inline and anexo.extensao == '.doc':
        return _pagina_preview_indisponivel(
            anexo,
            'Arquivos .doc antigos não têm pré-visualização no navegador. '
            'Baixe o arquivo para abrir no Word.')

    try:
        handle = anexo.arquivo.open('rb')
    except FileNotFoundError as exc:
        if inline:
            return _pagina_preview_indisponivel(
                anexo,
                'O arquivo não está disponível neste servidor '
                '(pode ter ficado só no sistema original). '
                'Peça o reenvio do anexo ou baixe de um backup de mídia.')
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
        msg = '; '.join(getattr(exc, 'messages', [str(exc)]))
        if _quer_json(request):
            return JsonResponse({'ok': False, 'mensagem': msg}, status=400)
        messages.error(request, msg)
        return _voltar_processo(processo.id)

    if _quer_json(request):
        return JsonResponse({
            'ok': True,
            'mensagem': (
                '1 arquivo anexado.' if len(salvos) == 1
                else f'{len(salvos)} arquivos anexados.'
            ) if salvos else (erros[0] if erros else 'Nenhum arquivo.'),
            'qtd_anexos': processo.anexos.count(),
            'anexos': [
                {'id': a.id, 'nome': a.nome_original, 'tamanho': a.tamanho_legivel}
                for a in processo.anexos.all().order_by('-id')[:20]
            ],
            'erros': erros,
        })

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
