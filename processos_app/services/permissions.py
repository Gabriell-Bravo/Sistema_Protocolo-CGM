# processos_app/services/permissions.py
"""
Ponto único de autorização do sistema (item 4).

Regras estruturais:
  - Nenhum nome de servidor aparece aqui. O acesso decorre do PAPEL (item 3).
  - Ocultar botão no template não é segurança: toda operação de escrita
    chama `assert_permissao` ou o decorador `exige` (item 4).
  - Gestão NÃO é Analista: não assume processo, não analisa, não libera
    assinatura (item 2).
  - `is_superuser` mantém o /admin e pode desfazer tramitação já avançada
    (análise, encaminhamento, retirada e saída). Não assume nem analisa.

Substitui os helpers que estavam em views.py:
    can_access_genero, filter_processes_by_user_level, is_analista,
    pode_usar_area_analista, pode_usar_gestao, pode_assumir_processos
"""

from functools import wraps

from django.core.exceptions import PermissionDenied

# --------------------------------------------------------------------------
# Papéis e grupos
# --------------------------------------------------------------------------

PROTOCOLO = 'PROTOCOLO'
ANALISTA_LICITACOES = 'ANALISTA_LICITACOES'
ANALISTA_LIQUIDACOES = 'ANALISTA_LIQUIDACOES'
GESTAO = 'GESTAO'

# Valores gravados hoje em Processo.genero. Continuam sendo a chave de
# grupo até a entrada de EspecieProcesso (Bloco C).
GRUPO_LICITACOES = 'LICITACOES_E_CONTRATOS'
GRUPO_LIQUIDACOES = 'LIQUIDACOES'

PAPEL_PARA_GRUPO = {
    ANALISTA_LICITACOES: GRUPO_LICITACOES,
    ANALISTA_LIQUIDACOES: GRUPO_LIQUIDACOES,
}

# Usado apenas pela migration 0015, na conversão de Profile.level.
# '3' era "Usuário Geral (Todos)": vira Gestão, ou seja, visão global sem
# atos técnicos. Quem de fato analisa precisa ser reclassificado
# nominalmente pela administração.
MAPA_NIVEL_LEGADO = {
    '0': PROTOCOLO,
    '1': ANALISTA_LICITACOES,
    '2': ANALISTA_LIQUIDACOES,
    '3': GESTAO,
}

PAPEL_PARA_NIVEL = {papel: nivel for nivel, papel in MAPA_NIVEL_LEGADO.items()}


# --------------------------------------------------------------------------
# Leitura do papel
# --------------------------------------------------------------------------

def get_papel(user):
    """Papel do usuário, ou None se não autenticado / sem profile."""
    if not user or not user.is_authenticated:
        return None
    profile = getattr(user, 'profile', None)
    if profile is None:
        return None
    papel = getattr(profile, 'papel', None)
    if papel:
        return papel
    # Fallback: o campo legado `level` ainda existe e não é apagado.
    return MAPA_NIVEL_LEGADO.get(getattr(profile, 'level', None))


def is_protocolo(user):
    return get_papel(user) == PROTOCOLO


def is_analista(user):
    return get_papel(user) in (ANALISTA_LICITACOES, ANALISTA_LIQUIDACOES)


def is_gestao(user):
    return get_papel(user) == GESTAO


def eh_administrador(user):
    """Superusuário do sistema. Não assume nem analisa no lugar do
    analista, mas desfaz tramitação e registra a saída como o Protocolo."""
    return bool(user and user.is_authenticated and user.is_superuser)


def grupo_do_analista(user):
    """Grupo de atuação do analista, ou None se o usuário não for analista."""
    return PAPEL_PARA_GRUPO.get(get_papel(user))


def nome_usuario(user):
    if not user:
        return ''
    return user.get_full_name() or user.username


def ids_com_sessao_ativa():
    """Usuários com sessão ainda válida: estão logados neste momento.

    A sessão padrão dura algumas horas e some no logout. Usuário
    desativado não entra aqui, mesmo que tenha restado uma sessão antiga.
    """
    from django.contrib.auth.models import User
    from django.contrib.sessions.models import Session
    from django.utils import timezone

    ids = set()
    agora = timezone.now()
    for sessao in Session.objects.filter(expire_date__gte=agora).iterator():
        uid = sessao.get_decoded().get('_auth_user_id')
        if uid is None:
            continue
        try:
            ids.add(int(uid))
        except (TypeError, ValueError):
            continue
    if not ids:
        return ids
    ativos = set(User.objects.filter(id__in=ids, is_active=True)
                 .values_list('id', flat=True))
    return ativos


def analistas_ativos():
    """Destinatários válidos para direcionamento de assinatura (item 8).

    Não filtra por grupo: o direcionamento pode cruzar grupos.
    Não filtra por disponibilidade: férias e curso são informação exibida
    no seletor, não bloqueio (item 9).
    """
    from django.contrib.auth.models import User
    return (User.objects
            .filter(is_active=True,
                    profile__papel__in=[ANALISTA_LICITACOES,
                                        ANALISTA_LIQUIDACOES])
            .select_related('profile')
            .order_by('first_name', 'username'))


def is_analista_ativo(user):
    return bool(user) and user.is_active and is_analista(user)


# --------------------------------------------------------------------------
# Acesso por grupo
# --------------------------------------------------------------------------

def pode_ver_grupo(user, grupo):
    """Visualização. Protocolo e Gestão veem todos os grupos."""
    if eh_administrador(user) or is_protocolo(user) or is_gestao(user):
        return True
    if is_analista(user):
        return not grupo or grupo_do_analista(user) == grupo
    return False


def pode_analisar_grupo(user, grupo):
    """Atos técnicos: assumir, analisar, liberar assinatura.

    Só o analista do próprio grupo. Gestão e Protocolo nunca (itens 2 e 3).
    """
    return is_analista(user) and grupo_do_analista(user) == grupo


def filtrar_por_grupo(user, queryset, campo='genero'):
    """Restringe um queryset ao que o usuário pode ver por grupo.

    `campo` indica onde está o gênero (ex.: 'genero' em Processo,
    'processo__genero' em Pendencia). Processos da CGM ficam de fora das
    listas comuns; a aba própria usa `apenas_processos_cgm`.
    """
    from .secretaria_cgm import excluir_processos_cgm

    via = campo.rsplit('__', 1)[0] if '__' in campo else ''

    if eh_administrador(user) or is_protocolo(user) or is_gestao(user):
        return excluir_processos_cgm(queryset, via=via)
    if is_analista(user):
        return excluir_processos_cgm(
            queryset.filter(**{campo: grupo_do_analista(user)}), via=via)
    return queryset.none()


# --------------------------------------------------------------------------
# Capacidades por ação
# --------------------------------------------------------------------------

def pode_cadastrar_processo(user):
    """item 2: a entrada do processo é do Protocolo."""
    return is_protocolo(user)


def pode_assumir_processo(user, processo):
    """Checa papel e grupo. Estado atual e trava de concorrência ficam em
    services/tramitacao.py, dentro da transação (item 39)."""
    from .secretaria_cgm import processo_e_da_cgm
    if processo_e_da_cgm(processo):
        return False
    return pode_analisar_grupo(user, processo.genero)


def pode_consultar_processo(user, processo):
    """Leitura da tela do processo: analista do grupo, Gestão e administrador.

    Processos da CGM: só Protocolo, Gestão e administrador.
    """
    from .secretaria_cgm import pode_ver_processos_cgm, processo_e_da_cgm
    if processo_e_da_cgm(processo):
        return pode_ver_processos_cgm(user)
    if eh_administrador(user) or is_gestao(user):
        return True
    return is_analista(user) and pode_ver_grupo(user, processo.genero)


def pode_declinar_analise(user, processo):
    """Devolver o processo à fila: quem assumiu, a Gestão ou o administrador."""
    if eh_administrador(user) or is_gestao(user):
        return True
    return is_analista(user) and processo.analista_responsavel_id == user.id


def pode_desfazer_tramite(user):
    """Desfazer o último avanço (análise, encaminhamento, retirada, saída)."""
    return eh_administrador(user)


def pode_devolver_da_assinatura(user):
    """Gestão devolve o que está com o Controlador, para corrigir a análise."""
    return is_gestao(user) or eh_administrador(user)


def pode_analisar_processo(user, processo):
    """Editar a análise: analista responsável, inclusive com o Controlador."""
    return (is_analista(user)
            and processo.analista_responsavel_id == user.id
            and processo.situacao_tramite in (
                'EM_ANALISE',
                'ASSINATURA_DIRECIONADA',
                'AGUARDANDO_ASSINATURA',
            ))


def pode_direcionar_assinatura(user, processo):
    """Somente o analista responsável encaminha a outro colega."""
    return is_analista(user) and processo.analista_responsavel_id == user.id


def pode_liberar_assinatura(user, processo):
    """item 11: o responsável (fluxo normal) ou o destinatário do
    direcionamento (assinatura substitutiva)."""
    if not is_analista(user):
        return False
    return user.id in (processo.analista_responsavel_id,
                       processo.assinatura_direcionada_para_id)


def pode_disponibilizar_retirada(user):
    """item 13: retorno físico do processo já assinado ao Protocolo."""
    return is_protocolo(user)


def pode_registrar_saida(user):
    """item 15. O administrador também registra a saída."""
    return is_protocolo(user) or eh_administrador(user)


def pode_alterar_destino(user):
    """item 16: alteração excepcional, ação própria do Protocolo."""
    return is_protocolo(user)


def pode_alterar_prioridade(user):
    """item 17: a prioridade é gerenciada pela Gestão."""
    return is_gestao(user)


def pode_indicar_atendimento(user):
    """item 29: apenas a Gestão."""
    return is_gestao(user)


def pode_consultar_finalizados(user):
    """Protocolo, Gestão e analista consultam. Só o Protocolo edita."""
    return is_protocolo(user) or is_gestao(user) or is_analista(user) or eh_administrador(user)


def pode_consultar_assinatura_e_diligencias(user):
    """Gestão age nessas filas; o analista só consulta o próprio grupo."""
    return is_gestao(user) or is_analista(user) or eh_administrador(user)


def pode_consultar_controle_relatorio(user):
    """Planilha de relatórios: Liquidações e administrador.

    Licitações usa o Controle de análise (lista de processos do grupo).
    """
    if eh_administrador(user):
        return True
    return grupo_do_analista(user) == GRUPO_LIQUIDACOES


def pode_nova_analise(user):
    """Nova análise pelo Controle: Liquidações, Licitações ou administrador."""
    if eh_administrador(user):
        return True
    return grupo_do_analista(user) in (GRUPO_LIQUIDACOES, GRUPO_LICITACOES)


def pode_definir_ultimo_relatorio(user):
    """Só o administrador informa o último número já usado."""
    return eh_administrador(user)


def pode_alterar_sequencia_relatorio(user):
    """Só o administrador troca o grupo de numeração de um processo."""
    return eh_administrador(user)


def pode_destinar_numeros_relatorio(user):
    """Administrador e analista de Liquidações guardam números para usar depois."""
    return eh_administrador(user) or grupo_do_analista(user) == GRUPO_LIQUIDACOES


def pode_editar_numero_relatorio(user, processo=None):
    """Administrador sempre; analista do grupo informa o próprio número."""
    if eh_administrador(user):
        return True
    if processo is None or not is_analista(user):
        return False
    if processo.genero != GRUPO_LIQUIDACOES:
        return False
    if not pode_consultar_processo(user, processo):
        return False
    if processo.analista_responsavel_id == user.id:
        return True
    return bool(processo.numero_relatorio)


def pode_editar_linha_relatorio(user, processo=None):
    """Corrige a análise já numerada (ou marcada sem relatório).

    Analista do grupo e administrador.
    """
    if eh_administrador(user):
        return True
    if not is_analista(user):
        return False
    if processo is None:
        return True
    return pode_consultar_processo(user, processo)


def pode_cancelar_linha_relatorio(user):
    """Cancela linha no Controle: guarda o número ou exclui da sequência."""
    return (
        eh_administrador(user)
        or is_gestao(user)
        or grupo_do_analista(user) == GRUPO_LIQUIDACOES
    )


def pode_apagar_linha_relatorio(user):
    """Apaga de verdade a linha do Controle (some da planilha). Só admin."""
    return eh_administrador(user)


def pode_resolver_pendencia(user, pendencia):
    """item 30: quem conclui tecnicamente é o responsável técnico."""
    return is_analista(user) and pendencia.responsavel_tecnico_id == user.id


def pode_criar_pendencia(user, processo):
    """item 25: a pendência nasce da análise técnica."""
    return pode_analisar_processo(user, processo)


def pode_ver_dashboard(user):
    return is_gestao(user) or eh_administrador(user)


def pode_gerir_pessoas(user):
    """item 23: módulo Gestão de Pessoas CGM."""
    return is_gestao(user)


def pode_cancelar_processo(user):
    """item 35: cancelamento lógico, nunca exclusão."""
    return is_gestao(user)


def pode_apagar_processo(user):
    """Exclusão do registro. Só o administrador, e só em processo ativo."""
    return eh_administrador(user)


def pode_editar_cadastros(user):
    """itens 19 a 22: cadastros parametrizáveis são da Gestão e do administrador."""
    return is_gestao(user) or eh_administrador(user)


def pode_acessar_fila_gestao(user):
    """Fila da Gestão de Processos: Gestão e administrador (para desfazer)."""
    return is_gestao(user) or eh_administrador(user)


def pode_anexar_arquivo(user, processo):
    """Anexar arquivo: analista de Licitações, no processo desse grupo.

    Não exige assumir, preencher análise, pendência ou encaminhamento.
    """
    if not user or not user.is_active or processo.esta_cancelado:
        return False
    return (get_papel(user) == ANALISTA_LICITACOES
            and processo.grupo == GRUPO_LICITACOES)


# --------------------------------------------------------------------------
# Tela inicial por papel (item 5)
# --------------------------------------------------------------------------

ROTA_INICIAL = {
    PROTOCOLO: 'listar_processos',
    ANALISTA_LICITACOES: 'area_analista',
    ANALISTA_LIQUIDACOES: 'area_analista',
    GESTAO: 'gestao_dashboard',
}


def rota_inicial(user):
    """Protocolo -> Área do Protocolo; Analista -> Minha Fila;
    Gestão -> Dashboard."""
    return ROTA_INICIAL.get(get_papel(user) or '', 'listar_processos')


# --------------------------------------------------------------------------
# Uso nas views
# --------------------------------------------------------------------------

def assert_permissao(condicao, mensagem='Você não tem permissão para esta ação.'):
    """Levanta PermissionDenied (403) sem expor detalhe interno (item 53)."""
    if not condicao:
        raise PermissionDenied(mensagem)


def exige(teste, mensagem='Você não tem permissão para esta ação.'):
    """Decorador de view a partir de um predicado sobre o usuário.

        @login_required
        @exige(is_protocolo)
        def registrar_saida(request): ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            assert_permissao(teste(request.user), mensagem)
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator


def contexto_de_permissoes(user):
    """Flags para os templates.

    Serve para exibir/ocultar controles. A decisão real é sempre refeita no
    backend, dentro do service da operação (item 4).
    """
    from .secretaria_cgm import pode_ver_processos_cgm
    return {
        'is_protocolo': is_protocolo(user),
        'is_analista': is_analista(user),
        'is_gestao': is_gestao(user),
        'grupo_analista': grupo_do_analista(user),
        'pode_cadastrar_processo': pode_cadastrar_processo(user),
        'pode_registrar_saida': pode_registrar_saida(user),
        'pode_alterar_destino': pode_alterar_destino(user),
        'pode_alterar_prioridade': pode_alterar_prioridade(user),
        'pode_indicar_atendimento': pode_indicar_atendimento(user),
        'pode_ver_dashboard': pode_ver_dashboard(user),
        'pode_gerir_pessoas': pode_gerir_pessoas(user),
        'pode_editar_cadastros': pode_editar_cadastros(user),
        'pode_cancelar_processo': pode_cancelar_processo(user),
        'pode_consultar_controle_relatorio': pode_consultar_controle_relatorio(user),
        'pode_nova_analise': pode_nova_analise(user),
        'pode_definir_ultimo_relatorio': pode_definir_ultimo_relatorio(user),
        'pode_destinar_numeros_relatorio': pode_destinar_numeros_relatorio(user),
        'pode_alterar_sequencia_relatorio': pode_alterar_sequencia_relatorio(user),
        'pode_editar_numero_relatorio': pode_editar_numero_relatorio(user),
        'pode_editar_linha_relatorio': pode_editar_linha_relatorio(user),
        'pode_cancelar_linha_relatorio': pode_cancelar_linha_relatorio(user),
        'pode_apagar_linha_relatorio': pode_apagar_linha_relatorio(user),
        'pode_desfazer_tramite': pode_desfazer_tramite(user),
        'pode_devolver_da_assinatura': pode_devolver_da_assinatura(user),
        'pode_acessar_fila_gestao': pode_acessar_fila_gestao(user),
        'pode_ver_processos_cgm': pode_ver_processos_cgm(user),
    }


def contexto_processor(request):
    """Flags de papel disponíveis em todos os templates."""
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return {
            'is_protocolo': False,
            'is_analista': False,
            'is_gestao': False,
            'grupo_analista': None,
            'pode_cadastrar_processo': False,
            'pode_registrar_saida': False,
            'pode_alterar_destino': False,
            'pode_alterar_prioridade': False,
            'pode_indicar_atendimento': False,
            'pode_ver_dashboard': False,
            'pode_gerir_pessoas': False,
            'pode_editar_cadastros': False,
            'pode_cancelar_processo': False,
            'pode_consultar_controle_relatorio': False,
            'pode_nova_analise': False,
            'pode_definir_ultimo_relatorio': False,
            'pode_destinar_numeros_relatorio': False,
            'pode_alterar_sequencia_relatorio': False,
            'pode_editar_numero_relatorio': False,
            'pode_editar_linha_relatorio': False,
            'pode_cancelar_linha_relatorio': False,
            'pode_apagar_linha_relatorio': False,
            'pode_desfazer_tramite': False,
            'pode_devolver_da_assinatura': False,
            'pode_acessar_fila_gestao': False,
            'pode_ver_processos_cgm': False,
        }
    return contexto_de_permissoes(user)
