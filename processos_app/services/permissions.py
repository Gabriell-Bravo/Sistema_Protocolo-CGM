# processos_app/services/permissions.py
"""
Ponto único de autorização do sistema (item 4).

Regras estruturais:
  - Nenhum nome de servidor aparece aqui. O acesso decorre do PAPEL (item 3)
    e, para Gestão/administrador, das funções extras escolhidas.
  - Ocultar botão no template não é segurança: toda operação de escrita
    chama `assert_permissao` ou o decorador `exige` (item 4).
  - Gestão, por padrão, NÃO é Analista. Pode somar Protocolo, Licitações
    e/ou Liquidações nas funções extras e então assume/analisa nesses grupos.
  - `is_superuser` mantém o /admin e pode desfazer tramitação já avançada.
    Também escolhe funções extras para operar como Protocolo ou analista.

Substitui os helpers que estavam em views.py:
    can_access_genero, filter_processes_by_user_level, is_analista,
    pode_usar_area_analista, pode_usar_gestao, pode_assumir_processos
"""

from functools import wraps

from django.core.exceptions import PermissionDenied
from django.utils import timezone

# --------------------------------------------------------------------------
# Papéis e grupos
# --------------------------------------------------------------------------

PROTOCOLO = 'PROTOCOLO'
ANALISTA_LICITACOES = 'ANALISTA_LICITACOES'
ANALISTA_LIQUIDACOES = 'ANALISTA_LIQUIDACOES'
GESTAO = 'GESTAO'
# Conta dedicada ao módulo LAI (Lei de Acesso à Informação): só enxerga a aba LAI.
LAI = 'LAI'

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

FUNCOES_ESCOLHIVEIS = (
    (PROTOCOLO, 'Protocolo'),
    (ANALISTA_LICITACOES, 'Licitações e Contratos'),
    (ANALISTA_LIQUIDACOES, 'Liquidações'),
)
CODIGOS_FUNCOES_ESCOLHIVEIS = {codigo for codigo, _ in FUNCOES_ESCOLHIVEIS}


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


def eh_administrador(user):
    """Superusuário do sistema. Desfaz tramitação avançada e gerencia contas."""
    return bool(user and user.is_authenticated and user.is_superuser)


def pode_escolher_funcoes(user):
    """Gestão e administrador marcam funções extras (Protocolo, análise)."""
    return eh_administrador(user) or get_papel(user) == GESTAO


def funcoes_extras(user):
    """Códigos extras gravados no perfil, se a conta puder escolhê-los."""
    if not pode_escolher_funcoes(user):
        return []
    profile = getattr(user, 'profile', None)
    if profile is None:
        return []
    brutos = getattr(profile, 'funcoes_extras', None) or []
    if not isinstance(brutos, (list, tuple)):
        return []
    papel = get_papel(user)
    return [
        codigo for codigo in brutos
        if codigo in CODIGOS_FUNCOES_ESCOLHIVEIS and codigo != papel
    ]


def funcoes_ativas(user):
    """Papel principal + funções extras (Gestão/admin)."""
    ativas = set()
    papel = get_papel(user)
    if papel:
        ativas.add(papel)
    ativas.update(funcoes_extras(user))
    return ativas


def tem_funcao(user, codigo):
    return codigo in funcoes_ativas(user)


def gravar_funcoes_extras(alvo, funcoes, autor):
    """Grava a seleção de funções extras. Só Gestão/admin; admin pode
    alterar a de outro Gestão/admin."""
    from ..models import Profile

    if not pode_escolher_funcoes(autor):
        raise PermissionDenied('Somente Gestão e administrador escolhem funções.')
    if alvo.id != autor.id and not eh_administrador(autor):
        raise PermissionDenied('Você só altera as próprias funções.')
    if not pode_escolher_funcoes(alvo):
        raise PermissionDenied(
            'Só contas de Gestão ou administrador recebem funções extras.')
    escolhidas = []
    papel = get_papel(alvo)
    for codigo in funcoes or []:
        if codigo in CODIGOS_FUNCOES_ESCOLHIVEIS and codigo != papel:
            if codigo not in escolhidas:
                escolhidas.append(codigo)
    profile, _ = Profile.objects.get_or_create(user=alvo)
    profile.funcoes_extras = escolhidas
    profile.save(update_fields=['funcoes_extras'])
    return escolhidas


def is_protocolo(user):
    return tem_funcao(user, PROTOCOLO)


def is_analista(user):
    return bool(funcoes_ativas(user) & {ANALISTA_LICITACOES, ANALISTA_LIQUIDACOES})


def is_gestao(user):
    return tem_funcao(user, GESTAO)


def is_lai(user):
    """Papel LAI (conta dedicada ao módulo). Não depende de função extra."""
    return get_papel(user) == LAI


def grupos_do_analista(user):
    """Grupos em que o usuário analisa (pode ser mais de um)."""
    ativas = funcoes_ativas(user)
    return {
        PAPEL_PARA_GRUPO[papel]
        for papel in (ANALISTA_LICITACOES, ANALISTA_LIQUIDACOES)
        if papel in ativas
    }


def grupo_do_analista(user):
    """Um grupo, ou None. Se a conta analisa os dois, devolve Licitações."""
    grupos = grupos_do_analista(user)
    if GRUPO_LICITACOES in grupos:
        return GRUPO_LICITACOES
    if GRUPO_LIQUIDACOES in grupos:
        return GRUPO_LIQUIDACOES
    return None


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


def _q_tem_funcao(codigo):
    """Papel principal ou função extra (Gestão/admin).

    Não usa JSONField `__contains`: o SQLite local não implementa esse
    lookup. As contas que escolhem extras são poucas (Gestão/admin).
    """
    from django.contrib.auth.models import User
    from django.db.models import Q

    q = Q(profile__papel=codigo)
    candidatos = (
        User.objects.filter(is_active=True)
        .filter(Q(profile__papel=GESTAO) | Q(is_superuser=True))
        .select_related('profile')
    )
    extras = [usuario.id for usuario in candidatos
              if codigo in funcoes_extras(usuario)]
    if extras:
        q |= Q(pk__in=extras)
    return q


def analistas_ativos():
    """Destinatários válidos para direcionamento de assinatura (item 8).

    Não filtra por grupo: o direcionamento pode cruzar grupos.
    Não filtra por disponibilidade: férias e curso são informação exibida
    no seletor, não bloqueio (item 9).
    """
    from django.contrib.auth.models import User
    return (User.objects
            .filter(is_active=True)
            .filter(
                _q_tem_funcao(ANALISTA_LICITACOES)
                | _q_tem_funcao(ANALISTA_LIQUIDACOES)
            )
            .select_related('profile')
            .distinct()
            .order_by('first_name', 'username'))


def analistas_do_grupo(grupo):
    """Analistas ativos do grupo (Relator na planilha / tela de análise)."""
    from django.contrib.auth.models import User
    if grupo == GRUPO_LICITACOES:
        codigo = ANALISTA_LICITACOES
    else:
        codigo = ANALISTA_LIQUIDACOES
    return (User.objects
            .filter(is_active=True)
            .filter(_q_tem_funcao(codigo))
            .select_related('profile')
            .distinct()
            .order_by('first_name', 'username'))


def opcoes_relator(grupo, nome_atual=''):
    """Nomes para o select de Relator; inclui o valor atual se for legado."""
    nomes = []
    vistos = set()
    for usuario in analistas_do_grupo(grupo):
        nome = (nome_usuario(usuario) or '').strip()
        chave = nome.casefold()
        if not nome or chave in vistos:
            continue
        nomes.append(nome)
        vistos.add(chave)
    atual = (nome_atual or '').strip()
    if atual and atual.casefold() not in vistos:
        nomes.insert(0, atual)
    return nomes


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
        return not grupo or grupo in grupos_do_analista(user)
    return False


def pode_analisar_grupo(user, grupo):
    """Atos técnicos: assumir, analisar, liberar assinatura.

    Só quem tem a função de analista daquele grupo (papel ou extra).
    """
    return is_analista(user) and grupo in grupos_do_analista(user)


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
        grupos = grupos_do_analista(user)
        if not grupos:
            return queryset.none()
        return excluir_processos_cgm(
            queryset.filter(**{f'{campo}__in': grupos}), via=via)
    return queryset.none()


# --------------------------------------------------------------------------
# Capacidades por ação
# --------------------------------------------------------------------------

def pode_cadastrar_processo(user):
    """item 2: a entrada do processo é do Protocolo."""
    return is_protocolo(user)


def pode_editar_lista_protocolo(user):
    """Edição em linha em Processos Protocolo (ativos e com saída).

    Protocolo corrige o cadastro no dia a dia. O administrador também,
    inclusive depois da saída física.
    """
    return is_protocolo(user) or eh_administrador(user)


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


def data_numero_relatorio(processo):
    """Data do nº de relatório (mesmo critério do Controle: data_analise)."""
    return getattr(processo, 'data_analise', None)


def numero_relatorio_de_outro_dia(processo):
    """Tem nº gerado cuja data não é hoje — não-admin não devolve à fila."""
    if not (getattr(processo, 'numero_relatorio', None) or '').strip():
        return False
    data = data_numero_relatorio(processo)
    if data is None:
        return True
    return data != timezone.localdate()


def pode_declinar_analise(user, processo):
    """Devolver o processo à fila: quem assumiu, a Gestão ou o administrador.

    Com número de relatório de outro dia, só o administrador devolve.
    """
    if eh_administrador(user):
        return True
    if numero_relatorio_de_outro_dia(processo):
        return False
    if is_gestao(user):
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
    """Legado: indicação ao analista. Preferir pode_concluir_pendencia."""
    return is_gestao(user) or eh_administrador(user)


def pode_concluir_pendencia(user):
    """Gestão e admin concluem a diligência direto (sem passar pelo analista)."""
    return is_gestao(user) or eh_administrador(user)


def pode_verificar_correcao_pendencia(user, pendencia, processo_atual):
    """Analista da passagem atual marca pendência antiga como corrigida.

    Liga pelo número do processo da pendência, que precisa ser um dos números da dupla
    nº + Processo origem/pagamento do processo atual (ordem irrelevante). Duas Liquidações
    que só compartilham a origem não se ligam. 18.245/2025 e 18245/2025 contam como o mesmo.
    """
    from .numeros import chaves_dupla_origem_pagamento, normalizar_numero

    if not processo_atual or not pendencia:
        return False
    if not pode_analisar_processo(user, processo_atual):
        return False
    if not pendencia.esta_aberta:
        return False
    if pendencia.processo_id == processo_atual.id:
        return False
    atuais = set(chaves_dupla_origem_pagamento(processo_atual))
    numero_da_pendencia = normalizar_numero(pendencia.processo.numero_processo)
    return bool(atuais and numero_da_pendencia and numero_da_pendencia in atuais)


def pode_desfazer_indicacao_atendimento(user):
    """O administrador desfaz uma indicação feita por engano.

    A Gestão indica; quem avalia de verdade continua sendo o analista.
    Sem a conta do analista, só o administrador volta a diligência
    para aguardar atendimento.
    """
    return eh_administrador(user)


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
    return GRUPO_LIQUIDACOES in grupos_do_analista(user)


def pode_consultar_controle_analise(user):
    """Lista de Licitações e Contratos: analista do grupo, Gestão e admin."""
    from . import controle_analise as svc_controle_analise
    return svc_controle_analise.pode_consultar(user)


def pode_nova_analise(user):
    """Nova análise pelo Controle: Liquidações, Licitações ou administrador."""
    if eh_administrador(user):
        return True
    return bool(grupos_do_analista(user) & {GRUPO_LIQUIDACOES, GRUPO_LICITACOES})


def pode_definir_ultimo_relatorio(user):
    """Só o administrador informa o último número já usado."""
    return eh_administrador(user)


def pode_alterar_sequencia_relatorio(user):
    """Só o administrador troca o grupo de numeração de um processo."""
    return eh_administrador(user)


def pode_destinar_numeros_relatorio(user):
    """Administrador e analista de Liquidações guardam números para usar depois."""
    return eh_administrador(user) or GRUPO_LIQUIDACOES in grupos_do_analista(user)


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
        or GRUPO_LIQUIDACOES in grupos_do_analista(user)
    )


def pode_apagar_linha_relatorio(user):
    """Apaga de verdade a linha do Controle (some da planilha). Só admin."""
    return eh_administrador(user)


def pode_resolver_pendencia(user, pendencia):
    """item 30: quem conclui tecnicamente é o responsável técnico."""
    return is_analista(user) and pendencia.responsavel_tecnico_id == user.id


def pode_criar_pendencia(user, processo):
    """item 25: nasce da análise; o administrador também pode incluir."""
    return pode_analisar_processo(user, processo) or eh_administrador(user)


def pode_cancelar_pendencia(user, pendencia):
    """item 32: responsável técnico, Gestão ou administrador."""
    return (
        pode_resolver_pendencia(user, pendencia)
        or is_gestao(user)
        or eh_administrador(user)
    )


def pode_editar_pendencia(user, pendencia):
    """Corrigir texto de diligência aberta: responsável, Gestão ou admin."""
    if not pendencia.esta_aberta:
        return False
    return (
        pode_resolver_pendencia(user, pendencia)
        or is_gestao(user)
        or eh_administrador(user)
    )


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
    """Anexar arquivo: analista do grupo do processo (Licitações ou Liquidações).

    Não exige assumir, preencher análise, pendência ou encaminhamento.
    Em Liquidações o anexo (relatório) é opcional para encaminhar.
    """
    if not user or not user.is_active or processo.esta_cancelado:
        return False
    grupo = processo.grupo
    if tem_funcao(user, ANALISTA_LICITACOES) and grupo == GRUPO_LICITACOES:
        return True
    if tem_funcao(user, ANALISTA_LIQUIDACOES) and grupo == GRUPO_LIQUIDACOES:
        return True
    return False


# --------------------------------------------------------------------------
# Tela inicial por papel (item 5)
# --------------------------------------------------------------------------

ROTA_INICIAL = {
    PROTOCOLO: 'listar_processos',
    ANALISTA_LICITACOES: 'area_analista',
    ANALISTA_LIQUIDACOES: 'area_analista',
    GESTAO: 'gestao_dashboard',
    LAI: 'lai:pendentes',
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
        'is_lai': is_lai(user),
        'grupo_analista': grupo_do_analista(user),
        'grupos_analista': grupos_do_analista(user),
        'pode_escolher_funcoes': pode_escolher_funcoes(user),
        'pode_cadastrar_processo': pode_cadastrar_processo(user),
        'pode_registrar_saida': pode_registrar_saida(user),
        'pode_alterar_destino': pode_alterar_destino(user),
        'pode_alterar_prioridade': pode_alterar_prioridade(user),
        'pode_indicar_atendimento': pode_indicar_atendimento(user),
        'pode_concluir_pendencia': pode_concluir_pendencia(user),
        'pode_desfazer_indicacao_atendimento': pode_desfazer_indicacao_atendimento(user),
        'pode_ver_dashboard': pode_ver_dashboard(user),
        'pode_gerir_pessoas': pode_gerir_pessoas(user),
        'pode_editar_cadastros': pode_editar_cadastros(user),
        'pode_cancelar_processo': pode_cancelar_processo(user),
        'pode_consultar_controle_relatorio': pode_consultar_controle_relatorio(user),
        'pode_consultar_controle_analise': pode_consultar_controle_analise(user),
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
            'is_lai': False,
            'grupo_analista': None,
            'grupos_analista': set(),
            'pode_escolher_funcoes': False,
            'pode_cadastrar_processo': False,
            'pode_registrar_saida': False,
            'pode_alterar_destino': False,
            'pode_alterar_prioridade': False,
            'pode_indicar_atendimento': False,
            'pode_concluir_pendencia': False,
            'pode_desfazer_indicacao_atendimento': False,
            'pode_ver_dashboard': False,
            'pode_gerir_pessoas': False,
            'pode_editar_cadastros': False,
            'pode_cancelar_processo': False,
            'pode_consultar_controle_relatorio': False,
            'pode_consultar_controle_analise': False,
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
