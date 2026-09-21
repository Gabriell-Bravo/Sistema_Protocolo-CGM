# processos/views.py
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from .models import (
    Processo, ProcessHistory, MonitoramentoRecord, Profile, Pendencia,
    SequenciaRelatorio, EventoProcesso,
)
import json
from datetime import datetime, date, timedelta, time
from django.db import transaction
from django.db.models import Q, Count, Case, When, IntegerField, Value, Exists, OuterRef
from django.db.models.functions import Coalesce
from django.contrib import messages
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required, user_passes_test
from .forms import AdminResetPasswordForm, CustomUserCreationForm
from django.contrib.auth.models import User
from .forms import ProcessoForm
import openpyxl
from openpyxl.styles import Font, Alignment, Border, Side
from django.utils import timezone, dateformat
from django.contrib.auth.forms import AuthenticationForm
from django.views.decorators.http import require_POST
import logging

logger = logging.getLogger(__name__)


from . import views_tramitacao
from .services import cadastros as svc_cadastros
from .services import indicadores
from .services import monitoramento as svc_monitoramento
from .services import pendencias as svc_pendencias
from .services import processos as svc_processos
from .services import permissions as perm
from .services import prazos as prazos_service
from .services import tramitacao
from .services.eventos import registrar_evento


# ---------------------------------------------------------------------
# Permissões: delegadas para services/permissions.py (item 4).
# As funções abaixo permanecem apenas como fachada, para não quebrar as
# chamadas existentes. Não acrescente regra de acesso aqui.
# ---------------------------------------------------------------------

def can_access_genero(user, genero):
    return perm.pode_ver_grupo(user, genero)


def filter_processes_by_user_level(user, queryset):
    return perm.filtrar_por_grupo(user, queryset)


def is_analista(user):
    return perm.is_analista(user)


def pode_usar_area_analista(user):
    """item 2: a Gestão NÃO é analista. Não acessa a área operacional."""
    return perm.is_analista(user)


def pode_usar_gestao(user):
    return perm.is_gestao(user)


def pode_assumir_processos(user):
    """item 2: somente analista assume processo."""
    return perm.is_analista(user)


def nome_usuario(user):
    return perm.nome_usuario(user)


def dias_prazo_por_prioridade(prioridade):
    return prazos_service.dias_por_prioridade(prioridade)


def normalizar_prioridade(valor):
    return prazos_service.normalizar_prioridade(valor)


def _can_access_genero_legado(user, genero):
    # MANTIDO APENAS COMO REFERÊNCIA DO COMPORTAMENTO ANTERIOR.
    # Nada no sistema chama esta função.
    if user.is_superuser:  # Superusers can access all
        return True

    try:
        user_level = user.profile.level
    except Profile.DoesNotExist:
        return False  # No profile, no access

    if user_level == '3':  # Usuário Geral can access all
        return True
    elif user_level == '1' and genero == 'LICITACOES_E_CONTRATOS':  # Analista 1 only Licitações
        return True
    elif user_level == '2' and genero == 'LIQUIDACOES':  # Analista 2 only Liquidações
        return True
    elif user_level == '0':  # Protocolo has no specific genre restrictions for general views, but specific functions
        return True
    return False

# Helper function to filter querysets by user level


def _filter_processes_by_user_level_legado(user, queryset):
    # MANTIDO APENAS COMO REFERÊNCIA. Nada no sistema chama esta função.
    if user.is_superuser:
        return queryset  # Superusers see all

    try:
        user_level = user.profile.level
    except Profile.DoesNotExist:
        return queryset.none()  # If no profile, no processes

    if user_level == '3':  # Usuário Geral sees all
        return queryset
    elif user_level == '1':  # Analista 1 sees only LICITACOES_E_CONTRATOS
        return queryset.filter(genero='LICITACOES_E_CONTRATOS')
    elif user_level == '2':  # Analista 2 sees only LIQUIDACOES
        return queryset.filter(genero='LIQUIDACOES')
    elif user_level == '0':  # Protocolo sees all processes, but might have limitations on functions
        return queryset
    return queryset.none()  # Default to no access if level is not recognized


def querystring_sem_page(request):
    """item 56: a paginação não pode perder os filtros aplicados."""
    parametros = request.GET.copy()
    parametros.pop('page', None)
    consulta = parametros.urlencode()
    return f'{consulta}&' if consulta else ''


def _data_ou_none(texto):
    try:
        return datetime.strptime(texto, '%Y-%m-%d').date() if texto else None
    except ValueError:
        return None


def _erro_json(exc, status=400):
    """Resposta JSON de erro sem expor exceção interna (item 53)."""
    if isinstance(exc, ValidationError):
        mensagem = '; '.join(exc.messages)
    elif isinstance(exc, PermissionDenied):
        mensagem = str(exc) or 'Você não tem permissão para esta ação.'
        status = 403
    else:
        logger.exception('Erro inesperado')
        mensagem = 'Não foi possível concluir a operação. Tente novamente ou acione o suporte.'
        status = 500
    return JsonResponse({"success": False, "message": mensagem}, status=status)


def prioridade_eh_destaque(prioridade):
    return prioridade in ('PRIORITARIO', 'URGENTE', 'SIM')


def ordem_fila(queryset):
    """Urgente → Prioritário → Normal → entrada mais antiga.

    item 22: a ordem vem do cadastro de Prioridades (campo `ordem`), então
    um código novo criado pela Gestão entra na posição certa. Registros sem
    vínculo com o cadastro usam a ordem equivalente fixa.
    """
    return queryset.annotate(
        _ordem_prioridade=Coalesce(
            'prioridade_fk__ordem',
            Case(
                When(prioridade='URGENTE', then=Value(10)),
                When(prioridade__in=['PRIORITARIO', 'SIM'], then=Value(20)),
                When(prioridade__in=['NORMAL', 'NAO'], then=Value(30)),
                default=Value(999),
                output_field=IntegerField(),
            ),
            # Tipos mistos (PositiveIntegerField x IntegerField) exigem
            # output_field explícito, senão o Django levanta FieldError.
            output_field=IntegerField(),
        )
    ).order_by('_ordem_prioridade', 'data_entrada', 'hora_entrada')


def anotar_situacao_fila(processos, user):
    for processo in processos:
        if processo.situacao_tramite == 'ASSINATURA_DIRECIONADA':
            if processo.assinatura_direcionada_para_id == user.id:
                # Destaque próprio: está esperando a SUA assinatura.
                processo.situacao_fila = 'direcionado_voce'
                processo.situacao_label = 'Assinatura direcionada a você'
                processo.situacao_class = 'badge--mine'
                processo.pode_liberar = True
            else:
                processo.situacao_fila = 'direcionado_outro'
                processo.situacao_label = (
                    f'Assinatura com {processo.nome_assinatura_direcionada}')
                processo.situacao_class = 'badge--other'
                processo.pode_liberar = False
            processo.pode_assumir = False
            processo.eh_meu = processo.analista_responsavel_id == user.id
        elif processo.situacao_tramite in ('AGUARDANDO_ASSINATURA',
                                          'DISPONIVEL_RETIRADA'):
            processo.situacao_fila = 'assinatura'
            processo.situacao_label = processo.get_situacao_tramite_display()
            processo.situacao_class = 'badge--primary'
            processo.pode_assumir = False
            processo.eh_meu = False
            processo.pode_liberar = False
        elif (processo.situacao_tramite == 'EM_ANALISE'
              and processo.analista_responsavel_id):
            if processo.analista_responsavel_id == user.id:
                processo.situacao_fila = 'voce'
                processo.situacao_label = 'Em análise por você'
                processo.situacao_class = 'badge--mine'
                processo.pode_assumir = False
                processo.eh_meu = True
                processo.pode_liberar = False
            else:
                processo.situacao_fila = 'outro'
                processo.situacao_label = (
                    f'Em análise por {processo.nome_analista}'
                )
                processo.situacao_class = 'badge--other'
                processo.pode_assumir = False
                processo.eh_meu = False
                processo.pode_liberar = False
        else:
            processo.situacao_fila = 'disponivel'
            processo.situacao_label = 'Disponível para análise'
            processo.situacao_class = 'badge--available'
            processo.pode_assumir = True
            processo.eh_meu = False
            processo.pode_liberar = False


def proximo_numero_relatorio():
    seq, _ = SequenciaRelatorio.objects.select_for_update().get_or_create(
        grupo='LIQUIDACOES',
        defaults={'proximo_numero': 1540},
    )
    max_existente = 1539
    for bruto in Processo.objects.filter(
        genero='LIQUIDACOES'
    ).exclude(numero_relatorio__isnull=True).exclude(
        numero_relatorio=''
    ).values_list('numero_relatorio', flat=True):
        try:
            max_existente = max(max_existente, int(str(bruto).strip()))
        except (TypeError, ValueError):
            continue
    numero = max(seq.proximo_numero, max_existente + 1)
    seq.proximo_numero = numero + 1
    seq.save(update_fields=['proximo_numero'])
    return str(numero)


def anotar_total_passagens(processos):
    """Quantas vezes cada número de processo já entrou na CGM."""
    numeros = {getattr(p, 'numero_processo', None) or (p.get('numero_processo') if isinstance(p, dict) else None)
               for p in processos}
    numeros.discard(None)
    if not numeros:
        return
    counts = dict(
        Processo.objects.filter(numero_processo__in=numeros)
        .values('numero_processo')
        .annotate(n=Count('id'))
        .values_list('numero_processo', 'n')
    )
    for processo in processos:
        if isinstance(processo, dict):
            processo['total_passagens'] = counts.get(processo['numero_processo'], 1)
        else:
            processo.total_passagens = counts.get(processo.numero_processo, 1)


@login_required
def cadastrar_processo(request):
    """Tela de entrada do Protocolo (item 17).

    GET mostra o formulário, alimentado pelos cadastros (itens 19 a 21).
    POST de formulário tradicional usa a MESMA regra do salvar_processo
    (item 18): services/processos.criar_processo.
    """
    if not perm.pode_cadastrar_processo(request.user):
        return HttpResponse("Você não tem permissão para cadastrar novos processos.", status=403)

    if request.method == 'POST':
        try:
            svc_processos.criar_processo(request.POST.dict(), request.user)
        except (PermissionDenied, ValidationError) as exc:
            messages.error(request, '; '.join(getattr(exc, 'messages', [str(exc)])))
            return redirect('cadastrar_processo')
        messages.success(request, 'Processo cadastrado.')
        return redirect('listar_processos')

    return render(request, 'Formulario.html', {
        'dados_formulario': svc_cadastros.dados_para_formulario(),
    })


def calcular_prazo(data_entrada, prioridade_value):
    if not data_entrada or not prioridade_value:
        return None
    try:
        data_prazo = data_entrada + timedelta(
            days=dias_prazo_por_prioridade(prioridade_value))
        return data_prazo
    except Exception as e:
        print(f"Erro ao calcular prazo: {e}")
        return None


def formatar_prazo(dias_restantes):
    if dias_restantes < 0:
        return f"{abs(dias_restantes)} dia(s) atrasado"
    if dias_restantes == 0:
        return "Vence hoje"
    return f"{dias_restantes} dia(s) restante(s)"


def calcular_proxima_data_monitoramento(data_base, prazo_monitoramento_tipo):
    """Mantida por compatibilidade. item 41: meses reais de calendário
    (relativedelta), não múltiplos de 30 dias. Regra em
    services/monitoramento.py."""
    return svc_monitoramento.somar_periodo(data_base, prazo_monitoramento_tipo)


@login_required
def index(request):
    return render(request, 'Formulario.html')


@login_required
@require_POST
def salvar_processo(request):
    """Cadastro pelo formulário de entrada (JSON).

    Regra única em services/processos.criar_processo (item 18). Aqui não há
    mais: cálculo de monitoramento por nome de espécie (item 42), prazo por
    prioridade (item 17) nem aceite de técnico, despacho, observação e
    saída na entrada (item 17).
    """
    try:
        data = json.loads(request.body or b'{}')
    except ValueError:
        return JsonResponse({"success": False, "message": "Requisição inválida."}, status=400)
    try:
        processo = svc_processos.criar_processo(data, request.user)
    except Exception as exc:
        return _erro_json(exc)
    return JsonResponse({"success": True, "message": "Processo salvo!", "id": processo.id})


@login_required
def listar_processos(request):
    """Processos ativos (item 58): não saíram e não foram cancelados."""
    if is_analista(request.user):
        return redirect('area_analista')

    termo_pesquisa = request.GET.get('termo', '').strip()
    prioridade_filtro = request.GET.get('prioridade', 'todas')
    genero_filtro = request.GET.get('genero', 'todas')
    especie_filtro = request.GET.get('especie', 'todas')
    situacao_filtro = request.GET.get('situacao', 'todas')

    processos_query = filter_processes_by_user_level(
        request.user, tramitacao.ativos()).select_related(
            'analista_responsavel', 'prioridade_fk')

    if termo_pesquisa:
        processos_query = processos_query.filter(
            Q(numero_processo__icontains=termo_pesquisa) |
            Q(secretaria__icontains=termo_pesquisa) |
            Q(objeto__icontains=termo_pesquisa) |
            Q(contratada__icontains=termo_pesquisa) |
            Q(tecnico__icontains=termo_pesquisa) |
            Q(valor__icontains=termo_pesquisa) |
            Q(periodo__icontains=termo_pesquisa)
        )
    if prioridade_filtro != 'todas':
        processos_query = processos_query.filter(prioridade=prioridade_filtro)
    if genero_filtro != 'todas':
        if perm.pode_ver_grupo(request.user, genero_filtro):
            processos_query = processos_query.filter(genero=genero_filtro)
        else:
            processos_query = processos_query.none()
    if especie_filtro != 'todas':
        processos_query = processos_query.filter(especie=especie_filtro)
    if situacao_filtro in dict(Processo.SITUACAO_TRAMITE_CHOICES):
        processos_query = processos_query.filter(situacao_tramite=situacao_filtro)

    # Pendência calculada dos registros reais (item 31), numa consulta só.
    processos_query = processos_query.annotate(
        pendencias_abertas=Count('pendencias', filter=Q(
            pendencias__status__in=Pendencia.STATUS_ABERTOS), distinct=True),
        tem_evento_cadastro=Exists(EventoProcesso.objects.filter(
            processo=OuterRef('pk'), tipo='PROCESSO_CADASTRADO')),
    ).order_by('data_entrada', 'hora_entrada', 'id')

    # Totais sobre o conjunto filtrado (antes da paginação).
    # select_related(None) evita o FieldError do Django 5.2: um FK não pode
    # estar em select_related e ser omitido pelo only() ao mesmo tempo.
    hoje = timezone.localdate()
    total_atrasados = total_vence_hoje = total_prioritarios = 0
    for processo in processos_query.select_related(None).only(
            'id', 'data_entrada', 'prioridade'):
        dias = prazos_service.dias_restantes(processo, hoje)
        if dias is not None and dias < 0:
            total_atrasados += 1
        elif dias == 0:
            total_vence_hoje += 1
        if prioridade_eh_destaque(processo.prioridade):
            total_prioritarios += 1
    total_processos = processos_query.count()

    pagina = Paginator(processos_query, 50).get_page(request.GET.get('page'))
    processos = list(pagina)
    anotar_total_passagens(processos)
    pode_saida = perm.pode_registrar_saida(request.user)
    for processo in processos:
        prazos_service.anotar(processo, hoje)
        # Saída: fluxo normal só a partir de "Disponível para retirada"
        # (item 15); acervo anterior à nova tramitação tem via de transição.
        processo.pode_registrar_saida = pode_saida and (
            processo.situacao_tramite == 'DISPONIVEL_RETIRADA'
            or tramitacao.eh_legado(processo))
        processo.saida_legado = processo.situacao_tramite != 'DISPONIVEL_RETIRADA'

    all_generos = [g for g in Processo.objects.values_list('genero', flat=True)
                   .distinct().order_by('genero') if can_access_genero(request.user, g)]
    especies_base = Processo.objects.filter(genero__in=all_generos)
    if genero_filtro != 'todas' and can_access_genero(request.user, genero_filtro):
        especies_base = Processo.objects.filter(genero=genero_filtro)
    all_especies = especies_base.values_list('especie', flat=True).distinct().order_by('especie')

    return render(request, 'lista_processos.html', {
        'processos': processos,
        'pagina': pagina,
        'querystring': querystring_sem_page(request),
        'total_processos': total_processos,
        'total_atrasados': total_atrasados,
        'total_vence_hoje': total_vence_hoje,
        'total_prioritarios': total_prioritarios,
        'prioridade_filtro': prioridade_filtro,
        'termo_pesquisa': termo_pesquisa,
        'genero_filtro': genero_filtro,
        'especie_filtro': especie_filtro,
        'situacao_filtro': situacao_filtro,
        'situacoes': [c for c in Processo.SITUACAO_TRAMITE_CHOICES if c[0] in Processo.SITUACOES_ATIVAS],
        'prioridades': svc_cadastros.opcoes_prioridade(),
        'all_generos': all_generos,
        'all_especies': all_especies,
        # item 51: só o Protocolo corrige dados de protocolo nesta tela
        'can_edit': perm.is_protocolo(request.user),
        'can_delete': perm.pode_cancelar_processo(request.user),
        'can_mark_saida': pode_saida,
        'can_create_process': perm.pode_cadastrar_processo(request.user),
        'dados_formulario': svc_cadastros.dados_para_formulario(),
    })


@login_required
@require_POST
def atualizar_processo(request, id):
    """Edição em linha das listas (item 51: whitelist por papel).

    A regra está em services/processos.aplicar_edicao. Campos fora da
    whitelist do papel são recusados e informados na resposta.
    """
    try:
        data = json.loads(request.body or b'{}')
    except ValueError:
        return JsonResponse({"success": False, "message": "Requisição inválida."}, status=400)
    processo = get_object_or_404(Processo, id=id)
    if not can_access_genero(request.user, processo.genero):
        return JsonResponse({"success": False, "message": "Você não tem permissão para editar este processo."}, status=403)
    if not svc_processos.campos_editaveis(request.user, processo):
        return JsonResponse({"success": False, "message": "Seu papel não edita dados deste processo por esta tela."}, status=403)
    try:
        alteracoes, recusados = svc_processos.aplicar_edicao(processo, data, request.user)
    except Exception as exc:
        return _erro_json(exc)

    aviso = ''
    # Campos que a tela manda sempre e que não mudaram não geram aviso.
    recusados_relevantes = [c for c in recusados
                            if str(data.get(c) or '') != str(getattr(processo, c, '') or '')]
    if recusados_relevantes:
        aviso = ('Não foram gravados (fora do que o seu papel pode editar): '
                 + ', '.join(recusados_relevantes) + '.')
    return JsonResponse({
        "success": True,
        "message": f"Processo atualizado. {len(alteracoes)} campo(s) alterado(s).",
        "alterados": sorted(alteracoes),
        "recusados": recusados,
        "aviso": aviso,
    })


@login_required
@require_POST
def deletar_processo(request, id):
    """item 35: não excluir. A rota antiga cancela logicamente, com motivo,
    autor e horário — o registro é preservado.

    CORREÇÃO: a versão anterior exigia superusuário na view e Gestão no
    service; nenhum dos dois conseguia cancelar.
    """
    motivo = request.POST.get('motivo')
    if not motivo and request.body and request.content_type == 'application/json':
        try:
            motivo = json.loads(request.body).get('motivo')
        except ValueError:
            motivo = None
    try:
        tramitacao.cancelar_processo(id, request.user, motivo)
    except Exception as exc:
        return _erro_json(exc)
    return JsonResponse({'success': True, 'message': 'Processo cancelado. O registro foi preservado no histórico.'})


def montar_passagens(processo):
    """Lista todas as vezes que o processo entrou na CGM.

    Cada retorno do processo gera um novo registro com o mesmo numero_processo,
    entao as passagens sao os registros irmaos ordenados pela entrada.
    """
    registros = Processo.objects.filter(
        numero_processo=processo.numero_processo
    ).order_by('data_entrada', 'hora_entrada', 'id')

    hoje = date.today()
    passagens = []

    for ordem, registro in enumerate(registros, start=1):
        if registro.data_saida:
            dias_permanencia = (registro.data_saida - registro.data_entrada).days
        else:
            dias_permanencia = (hoje - registro.data_entrada).days

        passagens.append({
            'ordem': ordem,
            'process_id': registro.id,
            'is_atual': registro.id == processo.id,
            'em_andamento': registro.data_saida is None,
            'volume': registro.volume,
            'secretaria': registro.secretaria,
            'destino': registro.destino,
            'entrada': formatar_data_hora(registro.data_entrada, registro.hora_entrada),
            'saida': formatar_data_hora(registro.data_saida, registro.hora_saida),
            'dias_permanencia': dias_permanencia,
        })

    return passagens


def formatar_data_hora(data, hora):
    if not data:
        return None
    if not hora:
        return data.strftime('%d/%m/%Y')
    return f"{data.strftime('%d/%m/%Y')} às {hora.strftime('%H:%M')}"


@login_required
def ver_historico_processo(request, process_id):
    processo = get_object_or_404(Processo, id=process_id)
    if not can_access_genero(request.user, processo.genero):
        return HttpResponse("Você não tem permissão para visualizar o histórico deste processo.", status=403)

    history_records = ProcessHistory.objects.filter(
        process=processo).order_by('-changed_at')
    monitoramento_records = MonitoramentoRecord.objects.filter(
        processo=processo).order_by('-data_registro')

    formatted_history = []
    for record in history_records:
        rec_dict = {
            'field_name': record.field_name,
            'old_value': record.old_value,
            'new_value': record.new_value,
            'changed_at_formatted': dateformat.format(timezone.localtime(record.changed_at), 'd/m/Y H:i:s',),
            'changed_by_user': record.changed_by.username if record.changed_by else 'N/A'
        }
        formatted_history.append(rec_dict)

    formatted_monitoramento_records = []
    for record in monitoramento_records:
        mon_dict = {
            'data_registro': record.data_registro.strftime('%d/%m/%Y %H:%M:%S'),
            'observacao': record.observacao,
            'registrado_por': record.registrado_por.username if record.registrado_por else 'N/A'
        }
        formatted_monitoramento_records.append(mon_dict)

    passagens = montar_passagens(processo)

    return render(request, 'historico_processo.html', {
        'history': formatted_history,
        'monitoramento_records': formatted_monitoramento_records,
        'process_id': process_id,
        'process_number': processo.numero_processo,
        'passagens': passagens,
        'total_passagens': len(passagens),
        'pendencias': processo.pendencias.select_related(
            'criada_por', 'responsavel_tecnico').all(),
        # item 31: calculado dos registros reais, não do campo legado
        'tem_pendencia_aberta': processo.tem_pendencia_aberta,
        'eventos': processo.eventos.select_related('usuario').all(),
        # item 50: tempos do fluxo deste processo, calculados dos carimbos
        'tempos': indicadores.tempos_do_processo(processo),
    })


@login_required
@require_POST
def concluir_monitoramento(request, process_id):
    """item 44: concluir monitoramento NÃO registra saída física.

    CORREÇÃO: a versão anterior preenchia data_saida/hora_saida quando o
    processo não tinha saída — ou seja, "finalizava" o processo pelo botão
    de monitoramento. Também aceitava GET (item 43). As duas coisas saíram.
    """
    try:
        svc_monitoramento.concluir(process_id, request.user)
    except PermissionDenied as exc:
        return JsonResponse({"success": False, "message": str(exc)}, status=403)
    except ValidationError as exc:
        return JsonResponse({"success": False, "message": '; '.join(exc.messages)}, status=400)
    return JsonResponse({
        'success': True,
        'message': 'Monitoramento concluído. A situação física do processo não foi alterada.'
    })


@login_required
def listar_finalizados(request):
    """Processos que saíram fisicamente (item 58).

    CORREÇÃO (item 43): a versão anterior GRAVAVA o status de monitoramento
    ao abrir esta página (PENDENTE vencido virava ATRASADO; CONCLUIDO com
    nova data voltava a PENDENTE). Agora o status é calculado na exibição e
    no filtro; nada é gravado. Para persistir, usar o comando agendado
    `python manage.py atualizar_status_monitoramento`.
    """
    if is_analista(request.user):
        return redirect('area_analista')

    data_inicial_filtro = request.GET.get('data_inicial', '').strip()
    data_final_filtro = request.GET.get('data_final', '').strip()
    prioridade_filtro = request.GET.get('prioridade', 'todas')
    termo_pesquisa = request.GET.get('termo', '').strip()
    status_monitoramento_filtro = request.GET.get('status_monitoramento', 'todas')
    especie_filtro = request.GET.get('especie', 'todas')
    genero_filtro = request.GET.get('genero', 'todas')
    status_analise_filtro = request.GET.get('status_analise', 'todas')

    hoje = timezone.localdate()
    processos_query = filter_processes_by_user_level(
        request.user, tramitacao.finalizados())

    if termo_pesquisa:
        processos_query = processos_query.filter(
            Q(numero_processo__icontains=termo_pesquisa) |
            Q(secretaria__icontains=termo_pesquisa) |
            Q(objeto__icontains=termo_pesquisa) |
            Q(contratada__icontains=termo_pesquisa) |
            Q(tecnico__icontains=termo_pesquisa) |
            Q(valor__icontains=termo_pesquisa) |
            Q(periodo__icontains=termo_pesquisa)
        )

    if prioridade_filtro != 'todas':
        processos_query = processos_query.filter(prioridade=prioridade_filtro)

    data_inicial = _data_ou_none(data_inicial_filtro)
    data_final = _data_ou_none(data_final_filtro)
    if data_inicial:
        processos_query = processos_query.filter(data_saida__gte=data_inicial)
    if data_final:
        processos_query = processos_query.filter(data_saida__lte=data_final)

    if status_monitoramento_filtro != 'todas':
        processos_query = processos_query.filter(
            svc_monitoramento.filtro_status(status_monitoramento_filtro, hoje))

    if genero_filtro != 'todas':
        if perm.pode_ver_grupo(request.user, genero_filtro):
            processos_query = processos_query.filter(genero=genero_filtro)
        else:
            processos_query = processos_query.none()

    if especie_filtro != 'todas':
        processos_query = processos_query.filter(especie=especie_filtro)

    if status_analise_filtro != 'todas':
        processos_query = processos_query.filter(status_analise=status_analise_filtro)

    # Totais de monitoramento sobre o conjunto filtrado, antes da paginação.
    total_monitoramento_pendente = processos_query.filter(
        svc_monitoramento.filtro_status('PENDENTE', hoje)).count()
    total_monitoramento_atrasado = processos_query.filter(
        svc_monitoramento.filtro_status('ATRASADO', hoje)).count()
    total_monitoramento_concluido = processos_query.filter(
        svc_monitoramento.filtro_status('CONCLUIDO', hoje)).count()
    total_processos = processos_query.count()

    processos_query = processos_query.order_by('-data_saida', '-hora_saida', '-id')
    pagina = Paginator(processos_query, 50).get_page(request.GET.get('page'))

    processos_data = []
    for processo in pagina:
        prazos_service.anotar(processo, hoje)
        status_mon = svc_monitoramento.status_efetivo(processo, hoje)
        processos_data.append({
            'id': processo.id,
            'numero_processo': processo.numero_processo,
            'volume': processo.volume or '',
            'secretaria': processo.secretaria,
            'data_entrada': processo.data_entrada,
            'hora_entrada': processo.hora_entrada,
            'data_saida': processo.data_saida,
            'hora_saida': processo.hora_saida,
            'destino': processo.destino or '',
            'genero': processo.genero,
            'especie': processo.especie,
            'objeto': processo.objeto,
            'contratada': processo.contratada or '',
            'recorrente': processo.recorrente,
            'prioridade': processo.prioridade,
            'prioridade_display': processo.prioridade_display,
            'prioridade_badge_class': processo.prioridade_badge_class,
            'tecnico': processo.nome_analista,
            'numero_despacho': processo.numero_despacho or '',
            'observacao': processo.observacao or '',
            'prazo_formatado': processo.prazo_formatado,
            'prazo_monitoramento_display': processo.get_prazo_monitoramento_display(),
            'proxima_data_monitoramento_formatada': processo.proxima_data_monitoramento.strftime('%d/%m/%Y') if processo.proxima_data_monitoramento else '',
            'status_monitoramento_display': svc_monitoramento.ROTULOS_STATUS.get(status_mon, status_mon),
            'status_monitoramento_raw': status_mon,
            'valor': processo.valor or '',
            'periodo': processo.periodo or '',
            'status_analise': processo.status_analise,
            'status_analise_display': processo.get_status_analise_display(),
            # item 31: calculado dos registros reais
            'tem_pendencia_aberta': processo.tem_pendencia_aberta,
        })

    anotar_total_passagens(processos_data)

    all_generos = [g for g in Processo.objects.values_list('genero', flat=True)
                   .distinct().order_by('genero') if can_access_genero(request.user, g)]
    especies_base = Processo.objects.filter(genero__in=all_generos)
    if genero_filtro != 'todas' and can_access_genero(request.user, genero_filtro):
        especies_base = Processo.objects.filter(genero=genero_filtro)
    all_especies = especies_base.values_list('especie', flat=True).distinct().order_by('especie')

    all_status_analise = [
        {'value': choice[0], 'label': choice[1]}
        for choice in Processo.STATUS_ANALISE_CHOICES
    ]

    return render(request, 'finalizados.html', {
        'processos': processos_data,
        'pagina': pagina,
        'querystring': querystring_sem_page(request),
        'total_processos': total_processos,
        'total_monitoramento_pendente': total_monitoramento_pendente,
        'total_monitoramento_atrasado': total_monitoramento_atrasado,
        'total_monitoramento_concluido': total_monitoramento_concluido,
        'can_export': perm.is_protocolo(request.user) or perm.is_gestao(request.user),
        'prioridade_filtro': prioridade_filtro,
        'termo_pesquisa': termo_pesquisa,
        'data_inicial_filtro': data_inicial_filtro,
        'data_final_filtro': data_final_filtro,
        'status_monitoramento_filtro': status_monitoramento_filtro,
        'especie_filtro': especie_filtro,
        'genero_filtro': genero_filtro,
        'status_analise_filtro': status_analise_filtro,
        'all_generos': all_generos,
        'all_especies': all_especies,
        'all_status_analise': all_status_analise,
        'is_admin': request.user.is_superuser,
        # item 51: só o Protocolo corrige dados de protocolo
        'can_edit': perm.is_protocolo(request.user),
        'campos_editaveis': sorted(svc_processos.campos_editaveis(request.user)),
        'can_delete': perm.pode_cancelar_processo(request.user),
        'can_concluir_monitoramento': perm.is_analista(request.user) or perm.is_gestao(request.user),
        'dados_formulario': svc_cadastros.dados_para_formulario(),
    })


@login_required
@user_passes_test(lambda u: u.is_superuser or perm.is_protocolo(u) or perm.is_gestao(u))
def exportar_finalizados_excel(request):
    data_inicial_str = request.GET.get('data_inicial')
    data_final_str = request.GET.get('data_final')
    prioridade = request.GET.get('prioridade')
    termo_pesquisa = request.GET.get('termo')
    status_monitoramento = request.GET.get('status_monitoramento', 'todas')
    especie = request.GET.get('especie', 'todas')
    genero = request.GET.get('genero', 'todas')
    status_analise = request.GET.get('status_analise', 'todas')

    if not data_inicial_str or not data_final_str:
        return HttpResponse('{"success": false, "message": "Por favor, selecione uma Data Inicial e uma Data Final para exportar os processos por período."}',
                            content_type='application/json', status=400)

    try:
        data_inicial = datetime.strptime(data_inicial_str, '%Y-%m-%d').date()
        data_final = datetime.strptime(data_final_str, '%Y-%m-%d').date()
    except ValueError:
        return HttpResponse('{"success": false, "message": "Formato de data inválido. Use AAAA-MM-DD."}',
                            content_type='application/json', status=400)

    # Cancelados ficam fora (item 35): o registro existe, mas não é saída.
    processes = tramitacao.finalizados().filter(
        data_saida__range=[data_inicial, data_final]
    ).order_by('data_saida')

    processes = filter_processes_by_user_level(request.user, processes)

    if prioridade and prioridade != 'todas':
        processes = processes.filter(prioridade=prioridade)
    if termo_pesquisa:
        processes = processes.filter(
            Q(numero_processo__icontains=termo_pesquisa) |
            Q(secretaria__icontains=termo_pesquisa) |
            Q(destino__icontains=termo_pesquisa) |
            Q(genero__icontains=termo_pesquisa) |
            Q(especie__icontains=termo_pesquisa) |
            Q(objeto__icontains=termo_pesquisa) |
            Q(contratada__icontains=termo_pesquisa) |
            Q(tecnico__icontains=termo_pesquisa) |
            Q(observacao__icontains=termo_pesquisa) |
            Q(valor__icontains=termo_pesquisa) |
            Q(periodo__icontains=termo_pesquisa)
        )

    if status_monitoramento != 'todas':
        processes = processes.filter(
            svc_monitoramento.filtro_status(status_monitoramento))

    if genero and genero != 'todas':
        if can_access_genero(request.user, genero):
            processes = processes.filter(genero=genero)
        else:
            processes = processes.none()

    if especie and especie != 'todas':
        processes = processes.filter(especie=especie)

    if status_analise != 'todas':
        processes = processes.filter(status_analise=status_analise)

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Processos Finalizados"

    headers = [
        "N° Processo", "Volume", "Secretaria", "Data Entrada", "Hora Entrada",
        "Data Saída", "Hora Saída", "Destino", "Gênero", "Espécie", "Objeto",
        "Contratada", "Recorrente", "Prioridade", "Técnico", "N° Despacho",
        "Observação", "Valor"
    ]
    sheet.append(headers)

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = openpyxl.styles.PatternFill(
        start_color="4CAF50", end_color="4CAF50", fill_type="solid")
    thin_border = Border(left=Side(style='thin'),
                         right=Side(style='thin'),
                         top=Side(style='thin'),
                         bottom=Side(style='thin'))

    for col_num, header_title in enumerate(headers, 1):
        cell = sheet.cell(row=1, column=col_num)
        cell.value = header_title
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal='center', vertical='center')
        cell.border = thin_border

    for process in processes:
        row_data = [
            process.numero_processo,
            process.volume,
            process.secretaria,
            process.data_entrada.strftime(
                '%Y-%m-%d') if process.data_entrada else '',
            process.hora_entrada.strftime(
                '%H:%M') if process.hora_entrada else '',
            process.data_saida.strftime(
                '%Y-%m-%d') if process.data_saida else '',
            # Formatacao Excel
            process.hora_saida.strftime('%H:%M') if process.hora_saida else '',
            process.destino,
            process.genero,
            process.especie,
            process.objeto,
            process.contratada,
            process.recorrente,
            process.prioridade,
            process.tecnico,
            process.numero_despacho,
            process.observacao,
            process.valor,

        ]
        sheet.append(row_data)

    for row in sheet.iter_rows(min_row=2):
        for cell in row:
            cell.border = thin_border
            if cell.column_letter in ['K', 'O', 'P', 'Q', 'R', 'U', 'V', 'W']:
                cell.alignment = Alignment(wrapText=True, vertical='top')

    for column in sheet.columns:
        max_length = 0
        column_letter = column[0].column_letter
        for cell in column:
            try:
                if cell.value is not None:
                    cell_length = len(str(cell.value))
                    if cell_length > max_length:
                        max_length = cell_length
            except:
                pass

        adjusted_width = (max_length + 2)
        if column_letter in ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W']:
            sheet.column_dimensions[column_letter].width = min(
                adjusted_width, 100)
        else:
            sheet.column_dimensions[column_letter].width = adjusted_width

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename=processos_finalizados_{data_inicial_str}_a_{data_final_str}.xlsx'
    workbook.save(response)

    return response


@login_required
def get_process_by_number(request, numero_processo):
    try:
        processo = Processo.objects.filter(numero_processo=numero_processo).order_by(
            '-data_entrada', '-hora_entrada').first()

        if not processo:
            return JsonResponse({'message': 'Processo não encontrado'}, status=404)

        if not can_access_genero(request.user, processo.genero):
            return JsonResponse({"message": "Você não tem permissão para visualizar detalhes deste processo."}, status=403)

        data = {
            'numero_processo': processo.numero_processo,
            'volume': processo.volume,
            'secretaria': processo.secretaria,
            'data_entrada': processo.data_entrada.strftime('%Y-%m-%d') if processo.data_entrada else None,
            'hora_entrada': processo.hora_entrada.strftime('%H:%M') if processo.hora_entrada else None,
            'data_saida': processo.data_saida.strftime('%Y-%m-%d') if processo.data_saida else None,
            # Format Time object for JSON
            'hora_saida': processo.hora_saida.strftime('%H:%M') if processo.hora_saida else None,
            'destino': processo.destino,
            'genero': processo.genero,
            'especie': processo.especie,
            'objeto': processo.objeto,
            'contratada': processo.contratada,
            'recorrente': processo.recorrente,
            'prioridade': processo.prioridade,
            'tecnico': processo.tecnico,
            'data_analise': processo.data_analise.strftime('%Y-%m-%d') if processo.data_analise else None,
            'numero_despacho': processo.numero_despacho,
            'observacao': processo.observacao,
            'prazo_monitoramento': processo.prazo_monitoramento,
            'proxima_data_monitoramento': processo.proxima_data_monitoramento.strftime('%Y-%m-%d') if processo.proxima_data_monitoramento else None,
            'status_monitoramento': processo.status_monitoramento,
            'valor': processo.valor,
            'periodo': processo.periodo,
            'status_analise': processo.status_analise,
        }
        return JsonResponse(data)
    except Exception as e:
        print(f"Erro inesperado em get_process_by_number: {e}")
        return JsonResponse({'message': 'Erro interno do servidor'}, status=500)


@login_required
@require_POST
def marcar_saida_processo(request, process_id):
    """Botão de saída da lista de ativos.

    CORREÇÃO (item 15): a versão anterior gravava SAIDA_CONCLUIDA a partir
    de QUALQUER situação, pulando análise, assinatura e retirada. Agora:
      - fluxo normal: só "Disponível para retirada" (services.tramitacao);
      - acervo anterior à nova tramitação: via de transição própria,
        registrada como tal no histórico (tramitacao.registrar_saida_legado).
    """
    processo = get_object_or_404(Processo, id=process_id)
    try:
        if processo.situacao_tramite == 'DISPONIVEL_RETIRADA':
            tramitacao.registrar_saida([processo.id], request.user)
        else:
            tramitacao.registrar_saida_legado(processo.id, request.user)
    except Exception as exc:
        return _erro_json(exc)
    processo.refresh_from_db()
    return JsonResponse({
        "success": True,
        "message": "Saída registrada.",
        "data_saida": processo.data_saida.strftime('%Y-%m-%d') if processo.data_saida else '',
        "hora_saida": processo.hora_saida.strftime('%H:%M') if processo.hora_saida else '',
    })


def user_login(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(request, username=username, password=password)
            if user is not None:
                login(request, user)
                return redirect('index')
            else:
                return render(request, 'registration/login.html', {'form': form, 'error': 'Nome de usuário ou senha inválidos.'})
    else:
        form = AuthenticationForm()
    return render(request, 'registration/login.html', {'form': form})


@login_required
@user_passes_test(lambda u: u.is_superuser)
def register(request):
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            return redirect('manage_users')
        else:
            return render(request, 'registration/register.html', {'form': form})
    else:
        form = CustomUserCreationForm()
    return render(request, 'registration/register.html', {'form': form})


@login_required
@user_passes_test(lambda u: u.is_superuser or u.is_staff)
def manage_users(request):
    users = User.objects.all().order_by('username')
    users = users.select_related('profile')

    # item 3: o que governa o acesso é o papel, não o nível legado.
    user_levels = Profile.PAPEL_CHOICES

    return render(request, 'admin/manage_users.html', {'users': users, 'user_levels': user_levels})


@login_required
@user_passes_test(lambda u: u.is_superuser)
def update_user_level(request, user_id):
    if request.method == 'POST':
        user_to_update = get_object_or_404(User, id=user_id)
        if user_to_update.id == request.user.id or user_to_update.is_superuser:
            return redirect('manage_users')

        novo_papel = request.POST.get('level')
        validos = [c[0] for c in Profile.PAPEL_CHOICES]
        if novo_papel in validos:
            profile, _ = Profile.objects.get_or_create(user=user_to_update)
            anterior = profile.papel
            profile.papel = novo_papel
            profile.level = perm.PAPEL_PARA_NIVEL.get(novo_papel, profile.level)
            profile.save(update_fields=['papel', 'level'])
            if anterior != novo_papel:
                messages.success(
                    request,
                    f'{user_to_update.username}: papel alterado para '
                    f'{profile.get_papel_display()}.')
        else:
            messages.error(request, 'Papel inválido.')
        return redirect('manage_users')
    return redirect('manage_users')


@login_required
@user_passes_test(lambda u: u.is_superuser)
def delete_user(request, user_id):
    """item 36: não excluir usuário com histórico — desativar.

    A rota mantém o nome antigo. A ação alterna entre desativar e reativar:
    o usuário desativado não entra mais no sistema, mas continua como autor
    de análises, eventos e pendências.
    """
    if request.method == 'POST':
        alvo = get_object_or_404(User, id=user_id)
        if alvo.id == request.user.id:
            messages.error(request, 'Você não pode desativar o próprio usuário.')
            return redirect('manage_users')
        alvo.is_active = not alvo.is_active
        alvo.save(update_fields=['is_active'])
        messages.success(
            request,
            f'{alvo.username} foi {"reativado" if alvo.is_active else "desativado"}. '
            'O histórico dele foi preservado.')
    return redirect('manage_users')


def _encerrar_sessoes_do_usuario(usuario):
    """Encerra sessões abertas do usuário após a senha ser redefinida."""
    from django.contrib.sessions.models import Session

    agora = timezone.now()
    for sessao in Session.objects.filter(expire_date__gte=agora):
        dados = sessao.get_decoded()
        if str(dados.get('_auth_user_id')) == str(usuario.pk):
            sessao.delete()


@login_required
@user_passes_test(lambda u: u.is_superuser)
def reset_user_password(request, user_id):
    alvo = get_object_or_404(User, id=user_id)
    if alvo.id == request.user.id:
        messages.error(
            request,
            'Para alterar a sua senha, use a opção Alterar senha.')
        return redirect('password_change')

    if request.method == 'POST':
        form = AdminResetPasswordForm(alvo, request.POST)
        if form.is_valid():
            form.save()
            _encerrar_sessoes_do_usuario(alvo)
            messages.success(
                request,
                f'Senha de {alvo.username} redefinida. Informe a nova senha ao usuário.')
            return redirect('manage_users')
    else:
        form = AdminResetPasswordForm(alvo)

    return render(request, 'admin/reset_user_password.html', {
        'form': form,
        'alvo': alvo,
    })


@login_required
def get_especies_by_genero(request):
    genero = request.GET.get('genero')
    if genero and can_access_genero(request.user, genero):
        especies = Processo.objects.filter(genero=genero).values_list(
            'especie', flat=True).distinct().order_by('especie')
        return JsonResponse({'especies': list(especies)})
    return JsonResponse({'especies': []})


@login_required
def get_all_especies(request):
    allowed_generos = [g for g in Processo.objects.values_list(
        'genero', flat=True).distinct() if can_access_genero(request.user, g)]
    especies = Processo.objects.filter(genero__in=allowed_generos).values_list(
        'especie', flat=True).distinct().order_by('especie')
    return JsonResponse({'especies': list(especies)})


# ---------------------------------------------------------------------------
# Area do analista
# ---------------------------------------------------------------------------

# item 31: 'tem_pendencia' saiu. A existência de pendência é calculada dos
# registros reais (Processo.tem_pendencia_aberta), não declarada.
CAMPOS_ANALISE = [
    'valor',
    'destino',
    'periodo',
    'data_analise',
    'numero_despacho',
    'status_analise',
    'observacao',
]


# item 37: filtros da Minha Fila. Os da Gestão atendem aos cards do Dashboard.
FILTROS_ANALISTA = [
    ('todos', 'Todos'),
    ('disponiveis', 'Disponíveis'),
    ('comigo', 'Comigo'),
    ('direcionados', 'Direcionados para mim'),
    ('outros', 'Com outros'),
    ('liberados', 'Liberados para assinatura'),
    ('vencidos', 'Vencidos'),
]
FILTROS_GESTAO = [
    ('todos', 'Todos'),
    ('disponiveis', 'Disponíveis'),
    ('em_analise', 'Em análise'),
    ('direcionados_gestao', 'Assinatura direcionada'),
    ('liberados', 'Liberados para assinatura'),
    ('vencidos', 'Vencidos'),
    ('vence_hoje', 'Vencendo hoje'),
    ('urgentes', 'Urgentes'),
]


def filtrar_fila(processos, filtro, usuario):
    """Aplica um filtro da fila sobre processos já anotados (prazo e situação)."""
    uid = usuario.id
    regras = {
        'disponiveis': lambda p: p.situacao_tramite == 'DISPONIVEL',
        'comigo': lambda p: p.situacao_tramite == 'EM_ANALISE' and p.analista_responsavel_id == uid,
        'direcionados': lambda p: (p.situacao_tramite == 'ASSINATURA_DIRECIONADA'
                                   and p.assinatura_direcionada_para_id == uid),
        'outros': lambda p: (p.analista_responsavel_id is not None
                             and p.analista_responsavel_id != uid
                             and p.situacao_tramite in ('EM_ANALISE', 'ASSINATURA_DIRECIONADA')),
        'em_analise': lambda p: p.situacao_tramite in ('EM_ANALISE', 'ASSINATURA_DIRECIONADA'),
        'direcionados_gestao': lambda p: p.situacao_tramite == 'ASSINATURA_DIRECIONADA',
        'liberados': lambda p: p.situacao_tramite == 'AGUARDANDO_ASSINATURA',
        'vencidos': lambda p: p.prazo_status == 'atrasado',
        'vence_hoje': lambda p: p.prazo_status == 'hoje',
        'urgentes': lambda p: p.prioridade == 'URGENTE',
    }
    regra = regras.get(filtro)
    return [p for p in processos if regra(p)] if regra else list(processos)


def consultar_fila_grupos(request, opcoes_filtro=FILTROS_ANALISTA):
    """Fila dos dois grupos de análise, com busca e filtro (item 37).

    Devolve (todos, licitacoes, liquidacoes, termo, filtro, contagens).
    `todos` é o conjunto sem filtro — base dos totais do topo da tela.
    """
    termo_pesquisa = request.GET.get('pesquisa', '').strip()
    filtro = request.GET.get('filtro', 'todos')
    if filtro not in dict(opcoes_filtro):
        filtro = 'todos'

    base_query = tramitacao.ativos().filter(
        genero__in=['LICITACOES_E_CONTRATOS', 'LIQUIDACOES'],
    ).exclude(
        situacao_tramite='DISPONIVEL_RETIRADA'
    ).select_related('analista_responsavel', 'assinatura_direcionada_para',
                     'prioridade_fk')
    processos_query = filter_processes_by_user_level(request.user, base_query)

    if termo_pesquisa:
        processos_query = processos_query.filter(
            Q(numero_processo__icontains=termo_pesquisa) |
            Q(objeto__icontains=termo_pesquisa) |
            Q(contratada__icontains=termo_pesquisa) |
            Q(secretaria__icontains=termo_pesquisa)
        )

    processos = list(ordem_fila(processos_query))
    anotar_total_passagens(processos)
    anotar_situacao_fila(processos, request.user)
    hoje = timezone.localdate()
    for processo in processos:
        prazos_service.anotar(processo, hoje)

    contagens = [(chave, rotulo, len(filtrar_fila(processos, chave, request.user)))
                 for chave, rotulo in opcoes_filtro]
    filtrados = filtrar_fila(processos, filtro, request.user)
    licitacoes = [p for p in filtrados if p.genero == 'LICITACOES_E_CONTRATOS']
    liquidacoes = [p for p in filtrados if p.genero == 'LIQUIDACOES']
    return processos, licitacoes, liquidacoes, termo_pesquisa, filtro, contagens


@login_required
def inicio(request):
    # item 5: cada papel cai direto na sua área de trabalho.
    return redirect(perm.rota_inicial(request.user))


@login_required
def _inicio_legado(request):
    """Envia cada usuario para a area correspondente ao seu nivel de acesso."""
    if is_analista(request.user):
        return redirect('area_analista')
    if pode_usar_gestao(request.user) and not (
        hasattr(request.user, 'profile') and request.user.profile.level == '0'
    ) and not request.user.is_superuser:
        return redirect('gestao_processos')
    return redirect('listar_processos')


@login_required
@user_passes_test(pode_usar_area_analista)
def area_analista(request):
    processos, licitacoes, liquidacoes, termo_pesquisa, filtro, contagens = (
        consultar_fila_grupos(request, FILTROS_ANALISTA))

    total_disponiveis = sum(1 for p in processos if p.situacao_fila == 'disponivel')
    total_comigo = sum(1 for p in processos if p.situacao_fila == 'voce')
    total_atrasados = sum(1 for p in processos if p.prazo_status == 'atrasado')
    total_atendimentos = svc_pendencias.total_atendimentos_indicados(request.user)

    return render(request, 'analista/lista.html', {
        'total_atendimentos': total_atendimentos,
        'filtro_atual': filtro,
        'filtros_fila': contagens,
        'licitacoes': licitacoes,
        'liquidacoes': liquidacoes,
        'mostra_licitacoes': bool(licitacoes) or can_access_genero(
            request.user, 'LICITACOES_E_CONTRATOS'),
        'mostra_liquidacoes': bool(liquidacoes) or can_access_genero(
            request.user, 'LIQUIDACOES'),
        'total_processos': len(processos),
        'total_disponiveis': total_disponiveis,
        'total_comigo': total_comigo,
        'total_atrasados': total_atrasados,
        'termo_pesquisa': termo_pesquisa,
        'modo_gestao': False,
        'pode_assumir': pode_assumir_processos(request.user),
    })


@login_required
@user_passes_test(pode_usar_gestao)
def gestao_processos(request):
    processos, licitacoes, liquidacoes, termo_pesquisa, filtro, contagens = (
        consultar_fila_grupos(request, FILTROS_GESTAO))

    total_disponiveis = sum(1 for p in processos if p.situacao_fila == 'disponivel')
    total_em_analise = sum(1 for p in processos
                           if p.situacao_tramite in ('EM_ANALISE', 'ASSINATURA_DIRECIONADA'))
    total_urgentes = sum(1 for p in processos if p.prioridade == 'URGENTE')

    return render(request, 'gestao/processos.html', {
        'licitacoes': licitacoes,
        'liquidacoes': liquidacoes,
        'mostra_licitacoes': True,
        'mostra_liquidacoes': True,
        'total_processos': len(processos),
        'total_disponiveis': total_disponiveis,
        'total_em_analise': total_em_analise,
        'total_urgentes': total_urgentes,
        'termo_pesquisa': termo_pesquisa,
        'modo_gestao': True,
        'pode_assumir': False,
        'prioridades': svc_cadastros.opcoes_prioridade(),
        'filtro_atual': filtro,
        'filtros_fila': contagens,
    })


@login_required
@user_passes_test(pode_usar_gestao)
def gestao_alterar_prioridade(request, process_id):
    if request.method != 'POST':
        return redirect('gestao_processos')

    # Delegado para services/tramitacao.py (itens 17 e 52).
    try:
        processo = tramitacao.alterar_prioridade(
            process_id, request.user, request.POST.get('prioridade'))
    except (PermissionDenied, ValidationError) as exc:
        mensagens = getattr(exc, 'messages', [str(exc)])
        messages.error(request, '; '.join(mensagens))
        return redirect('gestao_processos')

    messages.success(
        request,
        f"Prioridade de {processo.numero_processo} atualizada para "
        f"{processo.get_prioridade_display()}."
    )
    return redirect('gestao_processos')


@login_required
@user_passes_test(pode_usar_area_analista)
def assumir_processo(request, process_id):
    # Delegado para services/tramitacao.py (itens 39 e 52).
    if request.method != 'POST':
        return redirect('area_analista')
    try:
        processo = tramitacao.assumir(process_id, request.user)
    except (PermissionDenied, ValidationError) as exc:
        mensagens = getattr(exc, 'messages', [str(exc)])
        messages.error(request, '; '.join(mensagens))
        return redirect('area_analista')

    messages.success(
        request, "Processo assumido. A análise ficou registrada em seu nome.")
    return redirect('analista_processo', process_id=processo.id)


@login_required
@user_passes_test(lambda u: perm.is_analista(u) or perm.is_gestao(u))
def analista_processo(request, process_id):
    """Tela do processo. Analista trabalha aqui; Gestão só consulta
    (item 2: visão global sem ato técnico). Todo POST exige analista."""
    processo = get_object_or_404(
        Processo.objects.select_related(
            'analista_responsavel', 'assinatura_direcionada_para',
            'liberado_assinatura_por'),
        id=process_id)

    if not can_access_genero(request.user, processo.genero):
        return HttpResponse(
            "Você não tem permissão para analisar este processo.", status=403)

    if request.method == 'POST' and not perm.is_analista(request.user):
        raise PermissionDenied('A Gestão consulta o processo, mas não pratica atos de análise.')

    anotar_situacao_fila([processo], request.user)
    eh_responsavel = processo.analista_responsavel_id == request.user.id
    pode_editar = (
        processo.situacao_tramite == 'EM_ANALISE' and eh_responsavel
    )
    # itens 8, 10 e 11
    pode_direcionar = perm.pode_direcionar_assinatura(request.user, processo) and (
        processo.situacao_tramite in ('EM_ANALISE', 'ASSINATURA_DIRECIONADA'))
    assinatura_para_mim = (
        processo.situacao_tramite == 'ASSINATURA_DIRECIONADA'
        and processo.assinatura_direcionada_para_id == request.user.id
    )
    pode_liberar = (
        (processo.situacao_tramite == 'EM_ANALISE' and eh_responsavel)
        or assinatura_para_mim
    )

    if request.method == 'POST':
        acao = request.POST.get('acao', 'salvar')

        # Cada ação tem sua própria autorização (item 52). Quem recebeu a
        # assinatura direcionada libera, mas não edita a análise.
        permitido = {
            'salvar': pode_editar,
            'concluir': pode_liberar,
            'direcionar': pode_direcionar,
        }.get(acao, False)
        if not permitido:
            messages.error(
                request, "Você não tem permissão para esta ação neste processo.")
            return redirect('analista_processo', process_id=processo.id)

        try:
            alteracoes = registrar_analise(request, processo) if pode_editar else 0
        except ValidationError as exc:
            messages.error(request, '; '.join(exc.messages))
            return redirect('analista_processo', process_id=processo.id)

        if acao == 'concluir':
            # Liberação passa pelo service: valida completude da análise,
            # grava liberado_assinatura_por/em e registra o evento.
            try:
                tramitacao.liberar_assinatura(processo.id, request.user)
            except (PermissionDenied, ValidationError) as exc:
                messages.error(
                    request, '; '.join(getattr(exc, 'messages', [str(exc)])))
                return redirect('analista_processo', process_id=processo.id)
            messages.success(
                request, "Processo encaminhado para o Controlador.")
            return redirect('area_analista')

        if acao == 'direcionar':
            try:
                tramitacao.direcionar_assinatura(
                    processo.id, request.user, request.POST.get('destinatario'))
            except (PermissionDenied, ValidationError) as exc:
                messages.error(
                    request, '; '.join(getattr(exc, 'messages', [str(exc)])))
                return redirect('analista_processo', process_id=processo.id)
            messages.success(request, "Processo encaminhado para outro analista.")
            return redirect('analista_processo', process_id=processo.id)
        if alteracoes:
            messages.success(
                request, f"Análise salva. {alteracoes} campo(s) atualizado(s).")
        else:
            messages.info(request, "Nenhuma alteração para salvar.")
        return redirect('analista_processo', process_id=processo.id)

    prazo_obj = calcular_prazo(processo.data_entrada, processo.prioridade)
    if prazo_obj:
        dias_restantes = (prazo_obj - date.today()).days
        processo.prazo_formatado = formatar_prazo(dias_restantes)
        processo.prazo_status = (
            'atrasado' if dias_restantes < 0
            else 'hoje' if dias_restantes == 0
            else 'atencao' if dias_restantes <= 2
            else 'ok'
        )
    else:
        processo.prazo_formatado = "-"
        processo.prazo_status = 'indefinido'

    return render(request, 'analista/processo.html', {
        'processo': processo,
        'pendencias': processo.pendencias.select_related(
            'criada_por', 'responsavel_tecnico', 'atendimento_indicado_por',
            'cancelada_por').all(),
        'pendencias_anteriores': svc_pendencias.abertas_de_passagens_anteriores(
            processo),
        'somente_leitura': not perm.is_analista(request.user),
        'all_status_analise': Processo.STATUS_ANALISE_CHOICES,
        'passagens': montar_passagens(processo),
        'pode_editar': pode_editar,
        'eh_liquidacao': processo.genero == 'LIQUIDACOES',
        'pode_direcionar': pode_direcionar,
        'pode_liberar': pode_liberar,
        'assinatura_para_mim': assinatura_para_mim,
        'ja_direcionado': processo.situacao_tramite == 'ASSINATURA_DIRECIONADA',
        'campos_faltantes': tramitacao.campos_faltantes(processo),
        'analistas': views_tramitacao.opcoes_de_analistas(request.user),
        'pode_declinar': perm.pode_declinar_analise(request.user, processo)
                         and processo.situacao_tramite == 'EM_ANALISE',
    })


def registrar_analise(request, processo):
    """Grava os campos de análise (whitelist do analista, item 51).
    Regra em services/processos.aplicar_analise."""
    return svc_processos.aplicar_analise(processo, request.POST, request.user)


def texto_para_historico(campo, valor):
    if valor is None or valor == '':
        return ''
    if campo == 'status_analise':
        return dict(Processo.STATUS_ANALISE_CHOICES).get(valor, valor)
    if campo == 'prioridade':
        return dict(Processo.PRIORIDADE_CHOICES).get(valor, valor)
    if isinstance(valor, date):
        return valor.strftime('%Y-%m-%d')
    return str(valor)


@login_required
@user_passes_test(pode_usar_area_analista)
def adicionar_pendencia(request, process_id):
    processo = get_object_or_404(Processo, id=process_id)

    if not can_access_genero(request.user, processo.genero):
        return HttpResponse("Você não tem permissão para alterar este processo.", status=403)

    if request.method != 'POST':
        return redirect('analista_processo', process_id=processo.id)

    # Regras em services/pendencias.py: nasce AGUARDANDO_ATENDIMENTO com o
    # responsável técnico fixado (itens 25 e 27). O campo legado
    # tem_pendencia deixa de ser alimentado à mão (item 31).
    try:
        svc_pendencias.criar(
            processo.id, request.user, request.POST.get('descricao'))
        messages.success(request, "Pendência adicionada.")
    except (PermissionDenied, ValidationError) as exc:
        messages.error(request, '; '.join(getattr(exc, 'messages', [str(exc)])))
    return redirect('analista_processo', process_id=processo.id)


@login_required
@user_passes_test(pode_usar_area_analista)
def remover_pendencia(request, pendencia_id):
    pendencia = get_object_or_404(Pendencia, id=pendencia_id)
    processo = pendencia.processo

    if not can_access_genero(request.user, processo.genero):
        return HttpResponse("Você não tem permissão para alterar este processo.", status=403)

    if request.method != 'POST':
        return redirect('analista_processo', process_id=processo.id)

    # item 32: pendência não é apagada. Cadastrada indevidamente, é
    # cancelada — com motivo, autor e horário. A rota mantém o nome antigo
    # para não quebrar links, mas a ação é cancelar.
    try:
        svc_pendencias.cancelar(
            pendencia.id, request.user, request.POST.get('motivo'))
        messages.success(request, "Pendência cancelada. O registro foi preservado.")
    except (PermissionDenied, ValidationError) as exc:
        messages.error(request, '; '.join(getattr(exc, 'messages', [str(exc)])))
    return redirect('analista_processo', process_id=processo.id)
