# processos_app/views_pendencias.py
"""
Telas e endpoints de Pendências e Diligências (itens 28, 29, 30, 32, 34).

Views só tratam HTTP. As regras estão em services/pendencias.py.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Pendencia, Processo
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

def _diligencias_visiveis(usuario, status):
    return perm.filtrar_por_grupo(
        usuario, svc.fila_diligencias(status), campo='processo__genero')


ABAS_DILIGENCIA = (
    ('AGUARDANDO_ATENDIMENTO', 'Aguardando atendimento'),
    ('RESOLVIDA', 'Finalizados'),
)


@login_required
@perm.exige(perm.pode_consultar_assinatura_e_diligencias,
            'Área da Gestão e consulta dos analistas.')
def diligencias(request):
    """Lista diligências abertas ou finalizadas (todas do processo resolvidas).

    Gestão/admin concluem direto. Progresso do processo aparece como N/M.
    """
    status = request.GET.get('status', 'AGUARDANDO_ATENDIMENTO')
    if status == 'ATENDIMENTO_INDICADO':
        status = 'AGUARDANDO_ATENDIMENTO'
    if status not in dict(ABAS_DILIGENCIA) and status != 'ABERTAS':
        status = 'AGUARDANDO_ATENDIMENTO'
    termo = request.GET.get('termo', '').strip()

    lista = svc.filtrar_por_termo(
        _diligencias_visiveis(request.user, status), termo)
    if status == 'RESOLVIDA':
        from django.db.models import F
        lista = lista.order_by(F('resolvida_em').desc(nulls_last=True), '-id')
    pendencias = list(lista)
    svc.anotar_progresso(pendencias)
    titulos = dict(ABAS_DILIGENCIA)
    titulo_aba = titulos.get(status) or 'Aguardando atendimento'
    if status == 'ABERTAS':
        titulo_aba = 'Todas as abertas'
    return render(request, 'gestao/diligencias.html', {
        'pendencias': pendencias,
        'total': len(pendencias),
        'status_atual': status,
        'titulo_aba': titulo_aba,
        'status_choices': Pendencia.STATUS_CHOICES,
        'termo': termo,
        'abas_diligencia': [
            (chave, rotulo, _diligencias_visiveis(request.user, chave).count())
            for chave, rotulo in ABAS_DILIGENCIA
        ],
        **perm.contexto_de_permissoes(request.user),
    })


_MESES = (
    'janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho',
    'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro',
)


def _grupos_checklist(processo):
    """Diligências do processo, cada uma já separada em itens."""
    from .services.diligencia_texto import itens_para_checklist

    grupos = []
    pendencias = (processo.pendencias
                  .exclude(status='CANCELADA')
                  .select_related('responsavel_tecnico')
                  .order_by('criada_em'))
    for pendencia in pendencias:
        grupos.append({
            'pendencia': pendencia,
            'itens': itens_para_checklist(
                pendencia.descricao, pendencia.itens_concluidos),
        })
    return grupos


@login_required
@perm.exige(perm.pode_consultar_assinatura_e_diligencias,
            'Impressão do checklist é da Gestão, do administrador e dos analistas.')
def imprimir_checklist(request, process_id):
    """Folha de checklist das diligências de um processo, no padrão da CGM."""
    processo = get_object_or_404(Processo, id=process_id)
    if not perm.pode_consultar_processo(request.user, processo):
        raise PermissionDenied
    hoje = timezone.localdate()
    grupos = _grupos_checklist(processo)
    return render(request, 'gestao/checklist_impressao.html', {
        'processo': processo,
        'grupos': grupos,
        'varios': len(grupos) > 1,
        'data_extenso': (
            f'{hoje.day} de {_MESES[hoje.month - 1]} de {hoje.year}'),
    })


@login_required
@require_POST
def importar_planilha_diligencias(request):
    """Gestão/admin sobe o Excel CONTROLE DE PENDÊNCIAS."""
    from .services import importar_diligencias as svc_import

    try:
        resultado = svc_import.importar_planilha(
            request.user, request.FILES.get('planilha'))
        texto = (
            f'Importação: {resultado["criadas"]} diligência(s) nova(s)'
            f', {resultado["ignoradas"]} já existente(s) ignorada(s)'
            f' (de {resultado["lidas"]} linha(s) lida(s)).'
        )
        if resultado['processos_novos']:
            texto += (
                f' {resultado["processos_novos"]} processo(s) criado(s) '
                'para vincular pendências sem cadastro.')
        if resultado['saneadas']:
            texto += f' {resultado["saneadas"]} já veio(ram) com data de saneamento.'
        messages.success(request, texto)
    except (PermissionDenied, ValidationError) as exc:
        _erro(request, exc)
    return redirect('gestao_diligencias')


@login_required
@require_POST
def indicar_atendimento(request, pendencia_id):
    """Conclui a diligência (Gestão/admin). Mantém o nome da URL legado."""
    destino = request.POST.get('next') or 'gestao_diligencias'
    try:
        svc.concluir(
            pendencia_id, request.user,
            request.POST.getlist('itens_concluidos'))
        messages.success(request, 'Diligência concluída.')
    except (PermissionDenied, ValidationError) as exc:
        _erro(request, exc)
    if destino == 'gestao_diligencias' or not str(destino).startswith('/'):
        return redirect('gestao_diligencias')
    return redirect(destino)


@login_required
@require_POST
def concluir_pendencia(request, pendencia_id):
    """Gestão/admin marcam a diligência como completa."""
    return indicar_atendimento(request, pendencia_id)


@login_required
@require_POST
def desfazer_indicacao(request, pendencia_id):
    """O administrador volta uma indicação feita por engano."""
    destino = request.POST.get('next')
    try:
        svc.desfazer_indicacao(pendencia_id, request.user)
        messages.success(
            request,
            'Indicação desfeita. A diligência voltou a aguardar atendimento.')
    except (PermissionDenied, ValidationError) as exc:
        _erro(request, exc)
    if destino:
        return redirect(destino)
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
        messages.success(request, 'Diligência resolvida.')
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
            'Diligência devolvida. Ela reapareceu na fila de Diligências.')
    except (PermissionDenied, ValidationError) as exc:
        _erro(request, exc)
    return redirect(destino) if destino else _voltar_para_processo(pendencia_id)


@login_required
@require_POST
def cancelar_pendencia(request, pendencia_id):
    """item 32: cancelar exige motivo; a diligência não é apagada."""
    destino = request.POST.get('next')
    try:
        svc.cancelar(pendencia_id, request.user, request.POST.get('motivo'))
        messages.success(request, 'Diligência cancelada.')
    except (PermissionDenied, ValidationError) as exc:
        _erro(request, exc)
    return redirect(destino) if destino else _voltar_para_processo(pendencia_id)


@login_required
@require_POST
def editar_pendencia(request, pendencia_id):
    """Corrige o texto de diligência aberta (responsável, Gestão ou admin)."""
    destino = request.POST.get('next')
    try:
        svc.editar_descricao(
            pendencia_id, request.user, request.POST.get('descricao'))
        messages.success(request, 'Diligência atualizada.')
    except (PermissionDenied, ValidationError) as exc:
        _erro(request, exc)
    return redirect(destino) if destino else _voltar_para_processo(pendencia_id)
