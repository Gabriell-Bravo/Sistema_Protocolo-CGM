# processos_app/services/permissions.py
"""
Ponto único de autorização do sistema (item 4).

Regras estruturais:
  - Nenhum nome de servidor aparece aqui. O acesso decorre do PAPEL (item 3).
  - Ocultar botão no template não é segurança: toda operação de escrita
    chama `assert_permissao` ou o decorador `exige` (item 4).
  - Gestão NÃO é Analista: não assume processo, não analisa, não libera
    assinatura (item 2).
  - `is_superuser` mantém o /admin, mas não substitui papel em ato de
    tramitação.

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


def grupo_do_analista(user):
    """Grupo de atuação do analista, ou None se o usuário não for analista."""
    return PAPEL_PARA_GRUPO.get(get_papel(user))


def nome_usuario(user):
    if not user:
        return ''
    return user.get_full_name() or user.username


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
    if is_protocolo(user) or is_gestao(user):
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
    """Restringe um queryset de Processo ao que o usuário pode ver."""
    if is_protocolo(user) or is_gestao(user):
        return queryset
    if is_analista(user):
        return queryset.filter(**{campo: grupo_do_analista(user)})
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
    return pode_analisar_grupo(user, processo.genero)


def pode_analisar_processo(user, processo):
    """Editar a análise: só o analista que assumiu."""
    return (is_analista(user)
            and processo.analista_responsavel_id == user.id
            and processo.situacao_tramite in ('EM_ANALISE',
                                              'ASSINATURA_DIRECIONADA'))


def pode_direcionar_assinatura(user, processo):
    """item 8: somente o analista responsável pela análise. A Gestão apenas
    visualiza o direcionamento."""
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
    """item 15."""
    return is_protocolo(user)


def pode_alterar_destino(user):
    """item 16: alteração excepcional, ação própria do Protocolo."""
    return is_protocolo(user)


def pode_alterar_prioridade(user):
    """item 17: a prioridade é gerenciada pela Gestão."""
    return is_gestao(user)


def pode_indicar_atendimento(user):
    """item 29: apenas a Gestão."""
    return is_gestao(user)


def pode_resolver_pendencia(user, pendencia):
    """item 30: quem conclui tecnicamente é o responsável técnico."""
    return is_analista(user) and pendencia.responsavel_tecnico_id == user.id


def pode_criar_pendencia(user, processo):
    """item 25: a pendência nasce da análise técnica."""
    return pode_analisar_processo(user, processo)


def pode_ver_dashboard(user):
    return is_gestao(user)


def pode_gerir_pessoas(user):
    """item 23: módulo Gestão de Pessoas CGM."""
    return is_gestao(user)


def pode_cancelar_processo(user):
    """item 35: cancelamento lógico, nunca exclusão."""
    return is_gestao(user)


def pode_editar_cadastros(user):
    """itens 19 a 22: cadastros parametrizáveis são mantidos pela Gestão."""
    return is_gestao(user)


def pode_consultar_processo(user, processo):
    """Leitura da tela do processo: analista do grupo e Gestão (item 2)."""
    return is_gestao(user) or (is_analista(user) and pode_ver_grupo(user, processo.genero))


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
        }
    return contexto_de_permissoes(user)
