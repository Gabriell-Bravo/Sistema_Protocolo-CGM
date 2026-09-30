# processos_app/views_relatorios.py
"""Tela Controle de relatório: sequência (admin) e planilha (analista)."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from .services import permissions as perm
from .services import relatorios as svc


def _querystring_sem_page(request):
    parametros = request.GET.copy()
    parametros.pop('page', None)
    consulta = parametros.urlencode()
    return f'{consulta}&' if consulta else ''


@login_required
@perm.exige(perm.pode_consultar_controle_relatorio,
            'Área do analista e do administrador.')
def controle_relatorio(request):
    sequencia = svc.estado_sequencia()
    linhas = svc.listar(request.user)
    termo = request.GET.get('termo', '').strip()
    if termo:
        linhas = linhas.filter(
            Q(numero_processo__icontains=termo) |
            Q(numero_relatorio__icontains=termo) |
            Q(secretaria__icontains=termo) |
            Q(contratada__icontains=termo) |
            Q(analista__icontains=termo) |
            Q(objeto__icontains=termo)
        )
    total = linhas.count()
    pagina = Paginator(linhas, 50).get_page(request.GET.get('page'))
    return render(request, 'analista/controle_relatorio.html', {
        'sequencia': sequencia,
        'pagina': pagina,
        'linhas': pagina,
        'total': total,
        'termo': termo,
        'querystring': _querystring_sem_page(request),
        'pode_definir_ultimo': perm.pode_definir_ultimo_relatorio(request.user),
        **perm.contexto_de_permissoes(request.user),
    })


@login_required
@require_POST
def definir_ultimo_numero(request):
    perm.assert_permissao(
        perm.pode_definir_ultimo_relatorio(request.user),
        'Somente o administrador define o último número de relatório.')
    try:
        svc.definir_ultimo_numero(request.user, request.POST.get('ultimo_numero'))
    except (PermissionDenied, ValidationError) as exc:
        messages.error(request, '; '.join(getattr(exc, 'messages', [str(exc)])))
        return redirect('controle_relatorio')
    estado = svc.estado_sequencia()
    messages.success(
        request,
        f'Último relatório definido como {estado["ultimo"]}. '
        f'O próximo assumido receberá o nº {estado["proximo"]}.')
    return redirect('controle_relatorio')
