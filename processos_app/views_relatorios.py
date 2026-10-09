# processos_app/views_relatorios.py
"""Tela Controle de relatório: sequência (admin) e planilha (analista)."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from .models import Processo
from .services import cadastros as svc_cadastros
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


def _quer_json(request):
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return True
    accept = (request.headers.get('Accept') or '').lower()
    return 'application/json' in accept


def _resposta_linha_acao(request, grupo, secao='analises', ok=True, mensagem='',
                        extra=None):
    if _quer_json(request):
        payload = {'ok': ok, 'mensagem': mensagem, 'grupo': grupo}
        if extra:
            payload.update(extra)
        return JsonResponse(payload, status=200 if ok else 400)
    if mensagem:
        if ok:
            messages.success(request, mensagem)
        else:
            messages.error(request, mensagem)
    return redirect(_voltar_controle(grupo, secao))


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
    por_pagina = 200 if secao == 'analises' else 50
    pagina = Paginator(linhas, por_pagina).get_page(request.GET.get('page'))

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

    layout = svc.layout_planilha(grupo)
    template = (
        'analista/controle_relatorio_planilha.html'
        if secao == 'analises'
        else 'analista/controle_relatorio.html'
    )

    return render(request, template, {
        'aba': grupo,
        'secao': secao,
        'info_aba': info,
        'layout_planilha': layout,
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
        'secretarias': [u.nome for u in svc_cadastros.unidades_ativas()],
        'all_status_analise': Processo.STATUS_ANALISE_CHOICES,
        'sequencias_nova_analise': svc.sequencias_disponiveis(),
        'nova_analise_grupo': grupo,
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
def importar_planilha(request):
    """Admin importa Excel antigo para a planilha do Controle de relatório."""
    perm.assert_permissao(
        perm.pode_definir_ultimo_relatorio(request.user),
        'Somente o administrador importa planilha de relatório.')
    grupo = request.POST.get('grupo') or svc.GRUPO_PADRAO
    try:
        resultado = svc.importar_planilha_excel(
            request.user,
            request.FILES.get('planilha'),
            grupo=grupo,
        )
    except (PermissionDenied, ValidationError) as exc:
        messages.error(request, '; '.join(getattr(exc, 'messages', [str(exc)])))
        return redirect(_voltar_controle(grupo, 'numeracao'))
    if resultado.get('multi'):
        resumos = []
        for aba in resultado.get('abas') or []:
            trecho = (
                f'{aba["nome"]}: {aba["criadas"]} linha(s)'
                f', próximo nº {aba["proximo"]}')
            if aba.get('apagadas'):
                trecho += f', {aba["apagadas"]} antiga(s) substituída(s)'
            if aba['atualizadas']:
                trecho += f', {aba["atualizadas"]} sobrescrita(s) pelo Excel'
            if aba['ignoradas']:
                trecho += f', {aba["ignoradas"]} ignorada(s)'
            resumos.append(trecho)
        texto = (
            f'Importação completa — {resultado["criadas"]} linha(s) no total. '
            + ' · '.join(resumos)
        )
        puladas = resultado.get('puladas') or []
        if puladas:
            texto += (
                f' Abas não importadas (formato diferente ou duplicada): '
                f'{", ".join(puladas[:5])}'
                + ('…' if len(puladas) > 5 else '')
                + '.'
            )
        messages.success(request, texto)
        return redirect(_voltar_controle(svc.GRUPO_PADRAO, 'analises'))

    partes = [
        f'{resultado["nome"]}: {resultado["criadas"]} linha(s) importada(s)',
    ]
    if resultado.get('apagadas'):
        partes.append(
            f'{resultado["apagadas"]} antiga(s) do histórico substituída(s)')
    if resultado['atualizadas']:
        partes.append(
            f'{resultado["atualizadas"]} sobrescrita(s) pelo Excel')
    if resultado['ignoradas']:
        partes.append(f'{resultado["ignoradas"]} ignorada(s)')
    partes.append(f'próximo nº {resultado["proximo"]}')
    messages.success(request, '; '.join(partes) + '.')
    return redirect(_voltar_controle(grupo, 'analises'))


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
        desvinculados = getattr(processo, '_numeros_desvinculados', None) or []
        if desvinculados:
            lista = ', '.join(desvinculados)
            messages.warning(
                request,
                f'O número {processo.numero_relatorio} foi desvinculado '
                f'do processo {lista}.')
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
        processos = [
            (p or '').strip()
            for p in request.POST.getlist('processo')
            if (p or '').strip()
        ]
        numeros_brutos = request.POST.getlist('numero')
        pares = []
        for i, num_proc in enumerate(processos):
            bruto = numeros_brutos[i] if i < len(numeros_brutos) else ''
            pares.append((num_proc, bruto))
        resultado = svc.destinar_numeros(
            request.user,
            data=request.POST.get('data_relatorio'),
            grupo=grupo,
            pares=pares,
        )
        quantidade = resultado['quantidade']
        numeros = resultado['numeros']
        nome = svc.info_sequencia(grupo)['nome']
        if quantidade == 1:
            detalhe = f'nº {numeros[0]}'
        elif numeros == list(range(numeros[0], numeros[-1] + 1)):
            detalhe = f'nº {numeros[0]} a {numeros[-1]}'
        else:
            detalhe = 'nº ' + ', '.join(str(n) for n in numeros[:10])
            if quantidade > 10:
                detalhe += '…'
        messages.success(
            request,
            f'{quantidade} número{"s" if quantidade != 1 else ""} vinculado'
            f'{"s" if quantidade != 1 else ""} em {nome} ({detalhe}) '
            f'— linha amarela no Controle.')
    except (PermissionDenied, ValidationError) as exc:
        messages.error(request, '; '.join(getattr(exc, 'messages', [str(exc)])))
    return redirect(_voltar_controle(grupo, 'analises'))


@login_required
@require_GET
def sugerir_numeros(request):
    perm.assert_permissao(
        perm.pode_destinar_numeros_relatorio(request.user),
        'Somente analista de Liquidações e o administrador destinam números.')
    grupo = request.GET.get('grupo') or svc.GRUPO_PADRAO
    try:
        quantidade = int(request.GET.get('quantidade') or 0)
        excluir = [
            item.strip()
            for item in (request.GET.get('excluir') or '').split(',')
            if item.strip()
        ]
        numeros = svc.sugerir_numeros_disponiveis(
            grupo, quantidade, excluir=excluir or None)
        return JsonResponse({'numeros': numeros})
    except (PermissionDenied, ValidationError) as exc:
        return JsonResponse(
            {'erro': '; '.join(getattr(exc, 'messages', [str(exc)]))},
            status=400,
        )


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


@login_required
@require_POST
def cancelar_linha(request, linha_id):
    grupo = request.POST.get('grupo') or svc.GRUPO_PADRAO
    try:
        linha = svc.cancelar_linha(
            request.user, linha_id, request.POST.get('destino_numero'))
        if linha.sequencia:
            grupo = linha.sequencia
        return _resposta_linha_acao(
            request, grupo, ok=True,
            mensagem=(
                f'Relatório {linha.numero_relatorio} cancelado (vermelho). '
                f'Reuso só com número específico na análise.'
            ),
            extra={
                'linha_id': linha.id,
                'situacao_linha': linha.situacao_linha,
                'sem_relatorio': bool(linha.sem_relatorio),
                'css_class': getattr(linha, 'linha_css_class', '') or '',
            },
        )
    except (PermissionDenied, ValidationError) as exc:
        return _resposta_linha_acao(
            request, grupo, ok=False,
            mensagem='; '.join(getattr(exc, 'messages', [str(exc)])),
        )


@login_required
@require_POST
def desfazer_linha(request, linha_id):
    grupo = request.POST.get('grupo') or svc.GRUPO_PADRAO
    try:
        linha = svc.desfazer_linha(request.user, linha_id)
        if linha.sequencia:
            grupo = linha.sequencia
        if linha.situacao_linha == 'RESERVADA':
            mensagem = (
                f'Relatório {linha.numero_relatorio} desfeito (verde). '
                f'Disponível para reuso automático no mesmo dia.'
            )
        else:
            mensagem = (
                f'Relatório {linha.numero_relatorio} desfeito (vermelho). '
                f'Reuso só com número específico na análise.'
            )
        return _resposta_linha_acao(
            request, grupo, ok=True,
            mensagem=mensagem,
            extra={
                'linha_id': linha.id,
                'situacao_linha': linha.situacao_linha,
                'sem_relatorio': bool(linha.sem_relatorio),
                'css_class': getattr(linha, 'linha_css_class', '') or '',
            },
        )
    except (PermissionDenied, ValidationError) as exc:
        return _resposta_linha_acao(
            request, grupo, ok=False,
            mensagem='; '.join(getattr(exc, 'messages', [str(exc)])),
        )


@login_required
@require_POST
def editar_linha(request, linha_id):
    grupo = request.POST.get('grupo') or svc.GRUPO_PADRAO
    try:
        linha = svc.editar_linha(request.user, linha_id, request.POST)
        if linha.sequencia:
            grupo = linha.sequencia
        return _resposta_linha_acao(
            request, grupo, ok=True,
            mensagem=f'Linha do nº {linha.numero_relatorio or "—"} atualizada.',
            extra={
                'linha_id': linha.id,
                'numero_relatorio': linha.numero_relatorio or '',
                'sem_relatorio': bool(linha.sem_relatorio),
                'situacao_linha': linha.situacao_linha,
                'css_class': getattr(linha, 'linha_css_class', '') or '',
            },
        )
    except (PermissionDenied, ValidationError) as exc:
        return _resposta_linha_acao(
            request, grupo, ok=False,
            mensagem='; '.join(getattr(exc, 'messages', [str(exc)])),
        )


@login_required
@require_POST
def alternar_sem_relatorio(request, linha_id):
    grupo = request.POST.get('grupo') or svc.GRUPO_PADRAO
    try:
        linha = svc.alternar_sem_relatorio(request.user, linha_id)
        if linha.sequencia:
            grupo = linha.sequencia
        if linha.sem_relatorio:
            mensagem = (
                f'Nº {linha.numero_relatorio} marcado como sem relatório '
                f'(amarelo).'
            )
        else:
            mensagem = (
                f'Nº {linha.numero_relatorio}: marca de sem relatório removida.'
            )
        return _resposta_linha_acao(
            request, grupo, ok=True, mensagem=mensagem,
            extra={
                'linha_id': linha.id,
                'sem_relatorio': bool(linha.sem_relatorio),
                'situacao_linha': linha.situacao_linha,
                'css_class': getattr(linha, 'linha_css_class', '') or '',
            },
        )
    except (PermissionDenied, ValidationError) as exc:
        return _resposta_linha_acao(
            request, grupo, ok=False,
            mensagem='; '.join(getattr(exc, 'messages', [str(exc)])),
        )


@login_required
@require_POST
def vincular_processo_linha(request, linha_id):
    grupo = request.POST.get('grupo') or svc.GRUPO_PADRAO
    try:
        linha = svc.vincular_processo_linha(
            request.user, linha_id, request.POST.get('numero_processo'))
        if linha.sequencia:
            grupo = linha.sequencia
        if linha.processo_id:
            mensagem = (
                f'Número {linha.numero_relatorio} vinculado ao processo '
                f'{linha.numero_processo}.'
            )
        else:
            mensagem = (
                f'Nº {linha.numero_relatorio}: processo {linha.numero_processo} '
                f'informado e dados preenchidos na planilha.'
            )
        return _resposta_linha_acao(
            request, grupo, ok=True, mensagem=mensagem,
            extra={
                'linha_id': linha.id,
                'processo_id': linha.processo_id,
                'numero_processo': linha.numero_processo or '',
            },
        )
    except (PermissionDenied, ValidationError) as exc:
        return _resposta_linha_acao(
            request, grupo, ok=False,
            mensagem='; '.join(getattr(exc, 'messages', [str(exc)])),
        )


@login_required
@require_POST
def desvincular_processo_linha(request, linha_id):
    grupo = request.POST.get('grupo') or svc.GRUPO_PADRAO
    try:
        linha = svc.desvincular_processo_linha(request.user, linha_id)
        if linha.sequencia:
            grupo = linha.sequencia
        return _resposta_linha_acao(
            request, grupo, ok=True,
            mensagem=(
                f'Processo {linha.numero_processo or "—"} desvinculado do nº '
                f'{linha.numero_relatorio}. O número permanece na planilha.'
            ),
            extra={
                'linha_id': linha.id,
                'processo_id': None,
                'numero_processo': linha.numero_processo or '',
            },
        )
    except (PermissionDenied, ValidationError) as exc:
        return _resposta_linha_acao(
            request, grupo, ok=False,
            mensagem='; '.join(getattr(exc, 'messages', [str(exc)])),
        )


@login_required
@require_POST
def apagar_linha(request, linha_id):
    grupo = request.POST.get('grupo') or svc.GRUPO_PADRAO
    try:
        info = svc.apagar_linha(request.user, linha_id)
        numero = info.get('numero_relatorio') or '—'
        if info.get('sequencia'):
            grupo = info['sequencia']
        return _resposta_linha_acao(
            request, grupo, ok=True,
            mensagem=f'Linha do relatório {numero} apagada do Controle.',
            extra={'linha_id': linha_id, 'apagada': True},
        )
    except (PermissionDenied, ValidationError) as exc:
        return _resposta_linha_acao(
            request, grupo, ok=False,
            mensagem='; '.join(getattr(exc, 'messages', [str(exc)])),
        )


@login_required
@require_GET
@perm.exige(perm.pode_nova_analise,
            'Somente analista e o administrador iniciam Nova análise.')
def nova_analise_buscar(request):
    """JSON: auto-preenchimento do modal Nova análise."""
    grupo = (request.GET.get('grupo') or svc.GRUPO_PADRAO).strip()
    numero = (request.GET.get('numero_processo') or '').strip()
    try:
        payload = svc.buscar_para_nova_analise(request.user, numero, grupo)
        return JsonResponse({'ok': True, **payload})
    except (PermissionDenied, ValidationError) as exc:
        return JsonResponse({
            'ok': False,
            'mensagem': '; '.join(getattr(exc, 'messages', [str(exc)])),
        }, status=400)


@login_required
@require_POST
@perm.exige(perm.pode_nova_analise,
            'Somente analista e o administrador iniciam Nova análise.')
def nova_analise_salvar(request):
    """Salva análise/diligências; número só com Gerar número (trava + planilha)."""
    # QueryDict preserva getlist('diligencias'); .dict() ficaria só com a última.
    dados = request.POST
    grupo = dados.get('grupo') or svc.GRUPO_PADRAO
    try:
        resultado = svc.salvar_nova_analise(request.user, dados)
        return _resposta_linha_acao(
            request, grupo, ok=True,
            mensagem=resultado.get('mensagem') or 'Análise registrada.',
            extra=resultado,
        )
    except (PermissionDenied, ValidationError) as exc:
        return _resposta_linha_acao(
            request, grupo, ok=False,
            mensagem='; '.join(getattr(exc, 'messages', [str(exc)])),
        )
