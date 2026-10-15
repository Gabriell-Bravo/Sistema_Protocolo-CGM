"""Upload, preview e download dos arquivos do processo de Licitações."""

import mimetypes
from pathlib import Path

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import FileResponse, HttpResponse, JsonResponse
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


def _pagina_arquivo_indisponivel(anexo, motivo, *, status=404):
    """Página simples no lugar da tela técnica de erro."""
    from django.utils.html import escape

    nome = escape(anexo.nome_original or 'Arquivo')
    motivo = escape(motivo)
    return HttpResponse(
        '<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8">'
        f'<title>{nome}</title>'
        '<style>'
        'body{font-family:Segoe UI,Arial,sans-serif;margin:24px;color:#0f172a;'
        'background:#f8fafc;}'
        '.box{max-width:460px;margin:40px auto;padding:24px;background:#fff;'
        'border:1px solid #e2e8f0;border-radius:12px;text-align:center;}'
        'p{color:#64748b;line-height:1.5;}'
        '</style></head><body><div class="box">'
        f'<strong>{nome}</strong>'
        f'<p>{motivo}</p>'
        '</div></body></html>',
        content_type='text/html; charset=utf-8',
        status=status,
    )


def _servir_campo(anexo, campo, *, inline, filename, content_type):
    arquivo = getattr(anexo, campo, None)
    if not arquivo:
        return _pagina_arquivo_indisponivel(
            anexo,
            'Este arquivo não está neste servidor. '
            'Anexe o relatório de novo para visualizar e baixar.')
    try:
        handle = arquivo.open('rb')
    except OSError:
        return _pagina_arquivo_indisponivel(
            anexo,
            'Este arquivo não está neste servidor. '
            'Anexe o relatório de novo para visualizar e baixar.')
    return FileResponse(
        handle,
        as_attachment=not inline,
        filename=filename,
        content_type=content_type or 'application/octet-stream',
    )


def _abrir_anexo(anexo, usuario, *, inline=False, formato=''):
    perm.assert_permissao(
        perm.pode_ver_grupo(usuario, anexo.processo.grupo),
        'Você não tem permissão para ver este arquivo.')
    formato = (formato or '').lower()
    quer_pdf = formato == 'pdf' or (inline and anexo.extensao == '.docx')

    if anexo.extensao == '.docx' and quer_pdf:
        if svc.garantir_copia_pdf(anexo):
            nome_pdf = Path(anexo.nome_original or 'relatorio.docx').stem + '.pdf'
            return _servir_campo(
                anexo, 'arquivo_pdf', inline=inline,
                filename=nome_pdf, content_type='application/pdf')
        if inline:
            html = svc.html_preview_docx(anexo)
            if html:
                return HttpResponse(html, content_type='text/html; charset=utf-8')
        return _pagina_arquivo_indisponivel(
            anexo,
            'Não foi possível abrir este Word. '
            'O arquivo pode não estar mais no servidor. Anexe o relatório de novo.')

    if inline and anexo.extensao == '.doc':
        return _pagina_arquivo_indisponivel(
            anexo,
            'Arquivos .doc antigos não têm pré-visualização no navegador. '
            'Baixe o arquivo para abrir no Word.',
            status=200)

    content_type, _ = mimetypes.guess_type(anexo.nome_original or '')
    return _servir_campo(
        anexo, 'arquivo', inline=inline,
        filename=anexo.nome_original,
        content_type=content_type)


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
    return _abrir_anexo(
        anexo, request.user, inline=False,
        formato=request.GET.get('formato') or '')


@login_required
@xframe_options_sameorigin
def ver_anexo(request, anexo_id):
    """Abre o arquivo no navegador/iframe (preview), inclusive após a análise."""
    anexo = get_object_or_404(
        AnexoProcesso.objects.select_related('processo'), id=anexo_id)
    return _abrir_anexo(anexo, request.user, inline=True)
