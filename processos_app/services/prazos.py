# processos_app/services/prazos.py
"""
Política de prazos — ponto ÚNICO (itens 22 e 66).

=========================== DECISÃO PENDENTE ===========================
O documento de requisitos determina, no item 66, que duas questões NÃO
sejam decididas de forma autônoma:

  1. o prazo corre em dias corridos ou em dias úteis;
  2. ao mudar a prioridade, o prazo é recontado desde a entrada original
     ou desde a data da mudança.

Enquanto não houver definição administrativa, este módulo preserva o
comportamento que já vigorava: DIAS CORRIDOS, contados da DATA DE ENTRADA.
Para implementar a decisão, altere apenas as duas funções marcadas abaixo.
Nenhum outro arquivo do projeto deve calcular prazo.
=======================================================================
"""

import time
from datetime import timedelta

from django.db import DatabaseError
from django.utils import timezone

# Fallback: os valores que vigoravam antes do cadastro (item 22). Só são
# usados se a tabela `prioridades` ainda não existir ou não tiver o código.
PRAZO_POR_PRIORIDADE = {
    'URGENTE': 1,
    'PRIORITARIO': 2,
    'NORMAL': 7,
}

PRAZO_PADRAO = 7

# Equivalências legadas, gravadas antes da migration 0014.
NORMALIZACAO = {
    'SIM': 'PRIORITARIO',
    'NAO': 'NORMAL',
    'NÃO': 'NORMAL',
}

# Cache curto do cadastro: as listas calculam o prazo linha a linha e não
# podem gerar uma consulta por processo. Alterar o cadastro limpa o cache.
_CACHE_SEGUNDOS = 60
_cache = {'quando': 0.0, 'tabela': None}


def limpar_cache():
    _cache['quando'] = 0.0
    _cache['tabela'] = None


def tabela_prazos():
    """{codigo: prazo_dias} das prioridades cadastradas (ativas ou não:
    processo antigo com prioridade inativa continua tendo prazo)."""
    agora = time.monotonic()
    if _cache['tabela'] is not None and agora - _cache['quando'] < _CACHE_SEGUNDOS:
        return _cache['tabela']
    try:
        from ..models import Prioridade
        tabela = dict(Prioridade.objects.values_list('codigo', 'prazo_dias'))
    except DatabaseError:
        tabela = {}   # antes da migration 0016
    _cache['tabela'] = tabela
    _cache['quando'] = agora
    return tabela


def normalizar_prioridade(valor):
    """Código canônico. Aceita o código, o legado SIM/NAO ou um objeto
    Prioridade."""
    if not valor:
        return 'NORMAL'
    if hasattr(valor, 'codigo'):
        return valor.codigo
    valor = str(valor).strip().upper()
    valor = NORMALIZACAO.get(valor, valor)
    if valor in PRAZO_POR_PRIORIDADE or valor in tabela_prazos():
        return valor
    return 'NORMAL'


def dias_por_prioridade(prioridade):
    """Prazo em dias. Fonte: cadastro Prioridade (item 22)."""
    codigo = normalizar_prioridade(prioridade)
    tabela = tabela_prazos()
    if codigo in tabela:
        return tabela[codigo]
    return PRAZO_POR_PRIORIDADE.get(codigo, PRAZO_PADRAO)


# ----------------------------------------------------------------------
# DECISÃO PENDENTE nº 1 — dias corridos x dias úteis
# ----------------------------------------------------------------------
def somar_prazo(data_base, dias):
    """Hoje: dias corridos.

    Para dias úteis, substitua o corpo desta função por uma contagem que
    pule sábados, domingos e feriados municipais. Todo o sistema passa a
    usar a nova regra automaticamente.
    """
    if not data_base or dias is None:
        return None
    return data_base + timedelta(days=int(dias))


# ----------------------------------------------------------------------
# DECISÃO PENDENTE nº 2 — base de recontagem ao mudar a prioridade
# ----------------------------------------------------------------------
def data_base_do_prazo(processo, mudou_prioridade_em=None):
    """Hoje: sempre a data de entrada.

    Para recontar a partir da mudança de prioridade, devolva
    `mudou_prioridade_em or processo.data_entrada`.
    """
    return processo.data_entrada


def calcular_vencimento(processo, mudou_prioridade_em=None):
    """Data-limite do processo."""
    dias = dias_por_prioridade(processo.prioridade)
    base = data_base_do_prazo(processo, mudou_prioridade_em)
    return somar_prazo(base, dias)


def dias_restantes(processo, referencia=None):
    """Positivo: dias até o vencimento. Negativo: dias de atraso.
    None quando não há como calcular."""
    vencimento = calcular_vencimento(processo)
    if not vencimento:
        return None
    hoje = referencia or timezone.localdate()
    return (vencimento - hoje).days


def esta_vencido(processo, referencia=None):
    """item 37: filtro 'Vencidos'. Processo que já saiu não vence."""
    if not processo.esta_ativo:
        return False
    restantes = dias_restantes(processo, referencia)
    return restantes is not None and restantes < 0


def vence_hoje(processo, referencia=None):
    """item 47: card 'Vencendo hoje'."""
    if not processo.esta_ativo:
        return False
    return dias_restantes(processo, referencia) == 0


def formatar(dias):
    """Rótulo curto para as filas."""
    if dias is None:
        return ''
    if dias < 0:
        n = abs(dias)
        return f'Vencido há {n} dia' + ('s' if n > 1 else '')
    if dias == 0:
        return 'Vence hoje'
    return f'{dias} dia' + ('s' if dias > 1 else '')


def status_do_prazo(dias):
    """Classe visual usada pelas telas: atrasado, hoje, atencao, ok."""
    if dias is None:
        return 'indefinido'
    if dias < 0:
        return 'atrasado'
    if dias == 0:
        return 'hoje'
    if dias <= 2:
        return 'atencao'
    return 'ok'


def anotar(processo, referencia=None):
    """Grava no objeto (em memória, nada no banco) os atributos de prazo
    que as telas exibem. Substitui os blocos repetidos que existiam em
    cada view."""
    dias = dias_restantes(processo, referencia)
    processo.dias_restantes = dias
    processo.prazo_status = status_do_prazo(dias)
    if dias is None:
        processo.prazo_formatado = '-'
    elif dias < 0:
        processo.prazo_formatado = f'{abs(dias)} dia(s) atrasado'
    elif dias == 0:
        processo.prazo_formatado = 'Vence hoje'
    else:
        processo.prazo_formatado = f'{dias} dia(s) restante(s)'
    return processo
