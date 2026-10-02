# processos_app/views_relatorios.py
"""Tela Controle de relatório: sequência (admin) e planilha (analista)."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .services import permissions as perm
from .services import relatorios as svc


SECOES = ('analises', 'destinados', 'numeracao')


def _querystring_sem_page(request):
    parametros = request.GET.copy()
    parametros.pop('page', None)
    consulta = parametros.urlencode()
    return f'{consulta}&' if consulta else ''


def _voltar_controle(grupo=None, secao='analises'):
    grupo = grupo or svc.GRUPO_PADRAO
    if not svc.sequencia_valida(grupo):
        grupo = svc.GRUPO_PADRAO
    if secao not in SECOES:
        secao = 'analises'
    return f"{reverse('controle_relatorio')}?aba={grupo}&secao={secao}"


def _resolver_aba_secao(request, pode_destinar, pode_definir):
    """Aceita aba=grupo e secao=analises|destinados|numeracao; mantém links antigos."""
    bruto = (request.GET.get('aba') or '').strip()
    secao = (request.GET.get('secao') or '').strip()
    if bruto == 'destinados':
        return (
            svc.GRUPO_PADRAO,
            'destinados' if pode_destinar else 'analises',
        )
    if bruto == 'numeracao':
        return (
            svc.GRUPO_PADRAO,
            'numeracao' if pode_definir else 'analises',
        )
    if bruto == 'analises' or not bruto:
        grupo = svc.GRUPO_PADRAO
    elif svc.sequencia_valida(bruto):
        grupo = bruto
    else:
        grupo = svc.GRUPO_PADRAO
    if secao not in SECOES:
        secao = 'analises'
    if secao == 'destinados' and not pode_destinar:
        secao = 'analises'
    if secao == 'numeracao' and not pode_definir:
        secao = 'analises'
    return grupo, secao


@login_required
@perm.exige(perm.pode_consultar_controle_relatorio,
            'Área do analista e do administrador.')
def controle_relatorio(request):
    pode_destinar = perm.pode_destinar_numeros_relatorio(request.user)
    pode_definir = perm.pode_definir_ultimo_relatorio(request.user)
    grupo, secao = _resolver_aba_secao(request, pode_destinar, pode_definir)
    info = svc.info_sequencia(grupo)
    sequencia = svc.estado_sequencia(grupo)
    contagens = svc.contagens_por_sequencia(request.user)
    abas = [
        {
            **item,
            'total': contagens.get(item['codigo'], 0),
            'ativa': item['codigo'] == grupo,
        }
        for item in svc.sequencias_disponiveis()
    ]

    linhas = svc.listar(request.user, sequencia=grupo)
    termo = request.GET.get('termo', '').strip()
    if termo:
        linhas = svc.filtrar_por_termo(linhas, termo)
    total = linhas.count()
    pagina = Paginator(linhas, 50).get_page(request.GET.get('page'))

    reservas = []
    abas_reserva = []
    total_reservas = 0
    if pode_destinar:
        contagens_reserva = svc.contagens_reservas_por_sequencia()
        total_reservas = sum(contagens_reserva.values())
        abas_reserva = [
            {
                **item,
                'total': contagens_reserva.get(item['codigo'], 0),
                'ativa': item['codigo'] == grupo,
            }
            for item in svc.sequencias_disponiveis()
        ]
        reservas = svc.reservas_abertas(grupo)

    estados_numeracao = []
    if pode_definir:
        estados_numeracao = [
            {
                **item,
                **svc.estado_sequencia(item['codigo']),
            }
            for item in svc.sequencias_disponiveis()
        ]

    return render(request, 'analista/controle_relatorio.html', {
        'aba': grupo,
        'secao': secao,
        'info_aba': info,
        'abas': abas,
        'abas_reserva': abas_reserva,
        'grupos_destino': svc.sequencias_disponiveis(),
        'estados_numeracao': estados_numeracao,
        'sequencia': sequencia,
        'pagina': pagina,
        'linhas': pagina,
        'total': total,
        'total_reservas': total_reservas,
        'termo': termo,
        'querystring': _querystring_sem_page(request),
        'pode_definir_ultimo': pode_definir,
        'pode_destinar_numeros': pode_destinar,
        'reservas': reservas,
        **perm.contexto_de_permissoes(request.user),
    })


@login_required
@require_POST
def definir_ultimo_numero(request):
    perm.assert_permissao(
        perm.pode_definir_ultimo_relatorio(request.user),
        'Somente o administrador define o último número de relatório.')
    grupo = request.POST.get('grupo') or svc.GRUPO_PADRAO
    try:
        svc.definir_ultimo_numero(
            request.user, request.POST.get('ultimo_numero'), grupo=grupo)
    except (PermissionDenied, ValidationError) as exc:
        messages.error(request, '; '.join(getattr(exc, 'messages', [str(exc)])))
        return redirect(_voltar_controle(grupo, 'numeracao'))
    estado = svc.estado_sequencia(grupo)
    messages.success(
        request,
        f'{estado["nome"]}: último nº {estado["ultimo"]}. '
        f'O próximo relatório salvo receberá o nº {estado["proximo"]}.')
    return redirect(_voltar_controle(grupo, 'numeracao'))


@login_required
@require_POST
def alterar_numero(request, process_id):
    destino = request.POST.get('next') or ''
    if not destino.startswith('/'):
        destino = _voltar_controle()
    try:
        processo = svc.alterar_numero(
            request.user, process_id,
            request.POST.get('numero_relatorio'),
            request.POST.get('data_relatorio'))
        messages.success(
            request,
            f'Número do relatório de {processo.numero_processo} '
            f'atualizado para {processo.numero_relatorio}.')
    except (PermissionDenied, ValidationError) as exc:
        messages.error(request, '; '.join(getattr(exc, 'messages', [str(exc)])))
    return redirect(destino)


@login_required
@require_POST
def alterar_sequencia(request, process_id):
    destino = request.POST.get('next') or ''
    if not (destino.startswith('/') and not destino.startswith('//')):
        destino = reverse('analista_processo', args=[process_id])
    try:
        processo = svc.alterar_sequencia(
            request.user, process_id, request.POST.get('sequencia'))
        grupo = svc.sequencia_do_processo(processo) or svc.GRUPO_PADRAO
        nome = svc.info_sequencia(grupo)['nome']
        if processo.numero_relatorio:
            messages.success(
                request,
                f'{processo.numero_processo} passou para {nome}. '
                f'Novo número do relatório: {processo.numero_relatorio}.')
        else:
            messages.success(
                request,
                f'{processo.numero_processo} passou para {nome}.')
    except PermissionDenied:
        raise
    except ValidationError as exc:
        messages.error(request, '; '.join(getattr(exc, 'messages', [str(exc)])))
    return redirect(destino)


@login_required
@require_POST
def destinar_numeros(request):
    perm.assert_permissao(
        perm.pode_destinar_numeros_relatorio(request.user),
        'Somente analista de Liquidações e o administrador destinam números.')
    grupo = request.POST.get('grupo') or svc.GRUPO_PADRAO
    try:
        quantidade = svc.destinar_numeros(
            request.user,
            request.POST.get('numero_inicial'),
            request.POST.get('numero_final'),
            request.POST.get('data_relatorio'),
            grupo=grupo,
        )
        nome = svc.info_sequencia(grupo)['nome']
        messages.success(
            request,
            f'{quantidade} número{"s" if quantidade != 1 else ""} destinado'
            f'{"s" if quantidade != 1 else ""} em {nome}.')
    except (PermissionDenied, ValidationError) as exc:
        messages.error(request, '; '.join(getattr(exc, 'messages', [str(exc)])))
    return redirect(_voltar_controle(grupo, 'destinados'))


@login_required
@require_POST
def cancelar_destino(request, reserva_id):
    perm.assert_permissao(
        perm.pode_destinar_numeros_relatorio(request.user),
        'Somente analista de Liquidações e o administrador cancelam destinos.')
    grupo = request.POST.get('grupo') or svc.GRUPO_PADRAO
    try:
        numero = svc.cancelar_destino(request.user, reserva_id)
        messages.success(request, f'Destino do nº {numero} cancelado.')
    except (PermissionDenied, ValidationError) as exc:
        messages.error(request, '; '.join(getattr(exc, 'messages', [str(exc)])))
    return redirect(_voltar_controle(grupo, 'destinados'))
