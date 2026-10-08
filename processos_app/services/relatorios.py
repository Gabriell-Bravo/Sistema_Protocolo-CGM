# processos_app/services/relatorios.py
"""Controle de relatório: sequência numérica e planilha das análises.

Cada espécie de Liquidações pertence a uma sequência de numeração
(Liquidação, Adiantamento, Bolsa Atleta…). O administrador informa o
último número de cada sequência. O número é gerado ao salvar a análise.
"""

import re
import unicodedata
from datetime import date, datetime

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Case, Count, F, IntegerField, Q, Value, When
from django.db.models.functions import Cast
from django.utils import timezone

from ..models import (
    LinhaControleRelatorio, Processo, ReservaNumeroRelatorio, SequenciaRelatorio,
)
from . import permissions as perm
from .eventos import registrar_diff
from .processos import converter_data, formatar_valor


# Código legado da sequência geral (continua no banco como LIQUIDACOES).
GRUPO_PADRAO = perm.GRUPO_LIQUIDACOES
LIMITE_DESTINO = 80
# Importa todas as abas reconhecidas do .xlsx unificado (Controle Relatórios 2026).
GRUPO_IMPORTACAO_COMPLETA = '__TODAS__'

SEQUENCIAS = (
    {
        'codigo': GRUPO_PADRAO,
        'nome': 'Liquidação',
        'especies': (
            'Pagamento Geral',
            'Reanálise',
        ),
        'resumo': 'Inclui (Pagamento Geral; Reanálise).',
    },
    {
        'codigo': 'ADIANTAMENTO',
        'nome': 'Adiantamento',
        'especies': (
            'Concessão Adiantamento',
            'P.C. Adiantamento',
        ),
        'resumo': 'Inclui (Concessão Adiantamento; P.C. Adiantamento).',
    },
    {
        'codigo': 'COTA_PATROCINIO',
        'nome': 'Cota Patrocínio',
        'especies': (
            'Concessão Patrocínio',
            'P.C. Patrocínio',
        ),
        'resumo': 'Inclui (Concessão Patrocínio; P.C. Patrocínio).',
    },
    {
        'codigo': 'SUBVENCAO',
        'nome': 'Subvenção',
        'especies': (
            'Subvenção Social - Concessão',
            'Subvenção Social - Pagamento',
            'Subvenção Social - Prestação de Contas',
            'Subvenção Social - P.C. Anual',
            'Subvenção Social - Renovação',
        ),
        'resumo': (
            'Inclui (Subvenção Social - Concessão; Subvenção Social - Pagamento; '
            'Subvenção Social - Prestação de Contas; Subvenção Social - P.C. Anual; '
            'Subvenção Social - Renovação).'
        ),
    },
    {
        'codigo': 'ALUGUEL_SOCIAL',
        'nome': 'Aluguel Social',
        'especies': (
            'Concessão Aux. Aluguel Social',
        ),
        'resumo': 'Inclui (Concessão Aux. Aluguel Social).',
    },
    {
        'codigo': 'BOLSA_ATLETA',
        'nome': 'Bolsa Atleta',
        'especies': (
            'Concessão Aux. Bolsa Atleta',
            'P.C. Bolsa Atleta',
        ),
        'resumo': 'Inclui (Concessão Aux. Bolsa Atleta; P.C. Bolsa Atleta).',
    },
    {
        'codigo': 'AUXILIO_COMPETICAO',
        'nome': 'Auxílio Competição',
        'especies': (
            'Concessão Aux. Competição',
            'P.C. Aux. Competição',
        ),
        'resumo': (
            'Inclui (Concessão Aux. Competição; P.C. Aux. Competição).'
        ),
    },
    {
        'codigo': 'DIARIA',
        'nome': 'Diária',
        'especies': (
            'Concessão Diária',
        ),
        'resumo': 'Inclui (Concessão Diária).',
    },
    {
        'codigo': 'BLOCOS_CARNAVALESCOS',
        'nome': 'Blocos carnavalescos',
        'especies': (
            'Subvenção Bloco Carnaval',
            'P.C. Subvenção Bloco Carnaval',
        ),
        'resumo': (
            'Inclui (Subvenção Bloco Carnaval; '
            'P.C. Subvenção Bloco Carnaval).'
        ),
    },
)

_SEQUENCIA_POR_CODIGO = {item['codigo']: item for item in SEQUENCIAS}
_ESPECIE_PARA_SEQUENCIA = {
    nome.casefold(): item['codigo']
    for item in SEQUENCIAS
    for nome in item['especies']
}

# Sequências que já geram número próprio pela espécie.
SEQUENCIAS_ATIVAS = frozenset({
    GRUPO_PADRAO,
    'ADIANTAMENTO',
    'COTA_PATROCINIO',
    'SUBVENCAO',
    'ALUGUEL_SOCIAL',
    'BOLSA_ATLETA',
    'AUXILIO_COMPETICAO',
    'DIARIA',
    'BLOCOS_CARNAVALESCOS',
})


# Layout da planilha de Controle por grupo (rótulos iguais ao Excel 2026).
# Cada item: campo do modelo Processo/Linha → rótulo exibido.
# Campos extras da planilha (quant, modalidade…) reusam periodo/observacao.
_LAYOUT_PLANILHA = {
    GRUPO_PADRAO: {
        'titulo': 'Dados do relatório — Liquidação',
        'rotulos': {
            'analista': 'Relator',
            'numero_relatorio': 'Nº relatório',
            'data_relatorio': 'Data',
            'numero_processo': 'Nº processo',
            'secretaria': 'Secretaria',
            'objeto': 'Objeto',
            'periodo': 'Período',
            'valor': 'Valor',
            'destino': 'Destino',
            'contratada': 'Contratada / Favorecido',
            'observacao': 'Observação',
            'status_analise': 'Status da análise',
        },
        'colunas': (
            'numero_relatorio', 'data_relatorio', 'numero_processo', 'analista',
            'secretaria', 'objeto', 'valor', 'periodo', 'destino',
            'status_analise', 'observacao',
        ),
        'formulario': (
            'valor', 'destino', 'periodo', 'status_analise', 'observacao',
        ),
    },
    'ADIANTAMENTO': {
        'titulo': 'Dados do relatório — Adiantamento',
        'rotulos': {
            'numero_relatorio': 'Número',
            'contratada': 'Servidor',
            'valor': 'Valor',
            'numero_processo': 'Nº do Processo',
            'objeto': 'Assunto',
            'data_relatorio': 'Data',
            'destino': 'Enviado para',
            'secretaria': 'Secretaria de Origem',
            'analista': 'Analista / Relator',
            'observacao': 'Observação',
            'status_analise': 'Status da análise',
        },
        'colunas': (
            'numero_relatorio', 'contratada', 'valor', 'numero_processo',
            'objeto', 'data_relatorio', 'destino', 'secretaria', 'analista',
            'observacao',
        ),
        'formulario': (
            'contratada', 'valor', 'objeto', 'destino', 'secretaria',
            'status_analise', 'observacao',
        ),
    },
    'COTA_PATROCINIO': {
        'titulo': 'Dados do relatório — Cota Patrocínio',
        'rotulos': {
            'numero_relatorio': 'Número',
            'contratada': 'Interessado',
            'objeto': 'Evento',
            'valor': 'Valor',
            'numero_processo': 'Nº do Processo',
            'periodo': 'Assunto',
            'data_relatorio': 'Data',
            'destino': 'Enviado para',
            'observacao': 'OBS',
            'analista': 'Analista / Relator',
            'secretaria': 'Secretaria',
            'status_analise': 'Status da análise',
        },
        'colunas': (
            'numero_relatorio', 'contratada', 'objeto', 'valor',
            'numero_processo', 'periodo', 'data_relatorio', 'destino',
            'observacao',
        ),
        'formulario': (
            'contratada', 'objeto', 'valor', 'periodo', 'destino',
            'status_analise', 'observacao',
        ),
    },
    'SUBVENCAO': {
        'titulo': 'Dados do relatório — Subvenção',
        'rotulos': {
            'numero_relatorio': 'Número',
            'contratada': 'Entidade',
            'valor': 'Valor',
            'numero_processo': 'Nº do Processo',
            'periodo': 'Assunto',
            'objeto': 'Necessidade concessão/prestação',
            'data_relatorio': 'Data',
            'destino': 'Enviado para',
            'observacao': 'OBS',
            'analista': 'Analista / Relator',
            'secretaria': 'Secretaria',
            'status_analise': 'Status da análise',
        },
        'colunas': (
            'numero_relatorio', 'contratada', 'valor', 'numero_processo',
            'periodo', 'objeto', 'data_relatorio', 'destino', 'observacao',
        ),
        'formulario': (
            'contratada', 'valor', 'periodo', 'objeto', 'destino',
            'status_analise', 'observacao',
        ),
    },
    'ALUGUEL_SOCIAL': {
        'titulo': 'Dados do relatório — Aluguel Social',
        'rotulos': {
            'numero_relatorio': 'Número',
            'contratada': 'Beneficiário',
            'valor': 'Valor',
            'numero_processo': 'Nº do Processo',
            'objeto': 'Assunto',
            'data_relatorio': 'Data',
            'destino': 'Enviado para',
            'periodo': 'Parcelas',
            'observacao': 'OBS',
            'analista': 'Analista / Relator',
            'secretaria': 'Secretaria',
            'status_analise': 'Status da análise',
        },
        'colunas': (
            'numero_relatorio', 'contratada', 'valor', 'numero_processo',
            'objeto', 'data_relatorio', 'destino', 'periodo', 'observacao',
        ),
        'formulario': (
            'contratada', 'valor', 'objeto', 'destino', 'periodo',
            'status_analise', 'observacao',
        ),
    },
    'BOLSA_ATLETA': {
        'titulo': 'Dados do relatório — Bolsa Atleta',
        'rotulos': {
            'numero_relatorio': 'Número',
            'contratada': 'Nome do atleta',
            'periodo': 'Nome do responsável',
            'valor': 'Valor',
            'volume': 'Processo de concessão',
            'numero_processo': 'Processo de prestação',
            'objeto': 'Assunto / Modalidade',
            'data_relatorio': 'Data',
            'destino': 'Enviado para',
            'observacao': 'OBS',
            'analista': 'Analista / Relator',
            'secretaria': 'Secretaria',
            'status_analise': 'Status da análise',
        },
        'colunas': (
            'numero_relatorio', 'contratada', 'periodo', 'valor',
            'volume', 'numero_processo', 'objeto', 'data_relatorio',
            'destino', 'observacao',
        ),
        'formulario': (
            'contratada', 'periodo', 'valor',
            'processo_concessao', 'processo_prestacao',
            'objeto', 'destino', 'status_analise', 'observacao',
        ),
        'dicas': {
            'objeto': (
                'Informe o assunto e a modalidade '
                '(ex.: Prestação 2º semestre — Jiu-Jitsu).'
            ),
            'processo_concessao': 'Nº do processo de concessão da bolsa.',
            'processo_prestacao': 'Nº do processo de prestação de contas.',
        },
    },
    'AUXILIO_COMPETICAO': {
        'titulo': 'Dados do relatório — Auxílio Competição',
        'rotulos': {
            'numero_relatorio': 'Número',
            'contratada': 'Nome do atleta',
            'periodo': 'Nome do responsável',
            'valor': 'Valor',
            'volume': 'Processo de concessão',
            'numero_processo': 'Processo de prestação',
            'objeto': 'Assunto / Modalidade',
            'data_relatorio': 'Data',
            'destino': 'Enviado para',
            'observacao': 'OBS',
            'analista': 'Analista / Relator',
            'secretaria': 'Secretaria',
            'status_analise': 'Status da análise',
        },
        'colunas': (
            'numero_relatorio', 'contratada', 'periodo', 'valor',
            'volume', 'numero_processo', 'objeto', 'data_relatorio',
            'destino', 'observacao',
        ),
        'formulario': (
            'contratada', 'periodo', 'valor',
            'processo_concessao', 'processo_prestacao',
            'objeto', 'destino', 'status_analise', 'observacao',
        ),
        'dicas': {
            'processo_concessao': 'Nº do processo de concessão do auxílio.',
            'processo_prestacao': 'Nº do processo de prestação de contas.',
        },
    },
    'DIARIA': {
        'titulo': 'Dados do relatório — Diária',
        'rotulos': {
            'numero_relatorio': 'Número',
            'secretaria': 'Secretaria',
            'contratada': 'Servidor',
            'periodo': 'Quantidade',
            'valor': 'Valor total',
            'numero_processo': 'Nº do Processo',
            'objeto': 'Assunto',
            'data_relatorio': 'Data',
            'destino': 'Enviado para',
            'analista': 'Analista / Relator',
            'observacao': 'Observação',
            'status_analise': 'Status da análise',
        },
        'colunas': (
            'numero_relatorio', 'secretaria', 'contratada', 'periodo', 'valor',
            'numero_processo', 'objeto', 'data_relatorio', 'destino',
        ),
        'formulario': (
            'secretaria', 'contratada', 'periodo', 'valor', 'objeto',
            'destino', 'status_analise', 'observacao',
        ),
    },
    'BLOCOS_CARNAVALESCOS': {
        'titulo': 'Dados do relatório — Blocos carnavalescos',
        'rotulos': {
            'numero_relatorio': 'Número',
            'contratada': 'Bloco',
            'valor': 'Valor',
            'numero_processo': 'Nº do Processo',
            'objeto': 'Assunto',
            'data_relatorio': 'Data',
            'destino': 'Enviado para',
            'observacao': 'OBS',
            'analista': 'Analista / Relator',
            'secretaria': 'Secretaria',
            'status_analise': 'Status da análise',
        },
        'colunas': (
            'numero_relatorio', 'contratada', 'valor', 'numero_processo',
            'objeto', 'data_relatorio', 'destino', 'observacao',
        ),
        'formulario': (
            'contratada', 'valor', 'objeto', 'destino',
            'status_analise', 'observacao',
        ),
    },
}


def layout_planilha(codigo=None):
    """Rótulos e colunas iguais à planilha Excel do grupo."""
    codigo = codigo or GRUPO_PADRAO
    base = _LAYOUT_PLANILHA.get(GRUPO_PADRAO)
    layout = _LAYOUT_PLANILHA.get(codigo) or base
    rotulos = {**base['rotulos'], **layout.get('rotulos', {})}
    # Campos virtuais do formulário (Bolsa/Auxílio) usam rótulos próprios.
    rotulos.setdefault('processo_concessao', 'Processo de concessão')
    rotulos.setdefault('processo_prestacao', 'Processo de prestação')
    return {
        'codigo': codigo,
        'titulo': layout.get('titulo', base['titulo']),
        'rotulos': rotulos,
        'colunas': [
            {'campo': c, 'label': rotulos.get(c, c)}
            for c in layout.get('colunas', base['colunas'])
        ],
        'formulario': list(layout.get('formulario', base['formulario'])),
        'dicas': dict(layout.get('dicas') or {}),
    }


def _especie_e_prestacao(processo):
    """Espécie de prestação de contas (P.C.), não a concessão."""
    nome = ''
    especie = getattr(processo, 'especie_fk', None)
    if especie is not None:
        nome = especie.nome or ''
    if not nome:
        nome = getattr(processo, 'especie', None) or ''
    nome = str(nome).casefold()
    return (
        nome.startswith('p.c.')
        or 'prestação' in nome
        or 'prestacao' in nome
    )


def processos_relacionados_formulario(processo):
    """Campos editáveis Processo de concessão / prestação (Bolsa e Auxílio).

    Concessão = nº do processo (editável). Prestação começa vazia (editável).
    """
    sequencia = sequencia_do_processo(processo)
    if sequencia not in ('BOLSA_ATLETA', 'AUXILIO_COMPETICAO'):
        return None
    return {
        'concessao': (processo.numero_processo or '').strip(),
        'concessao_name': 'numero_processo',
        'concessao_readonly': False,
        'prestacao': (getattr(processo, 'processo_prestacao', None) or '').strip(),
        'prestacao_name': 'processo_prestacao',
        'prestacao_readonly': False,
    }


class RelatorioInvalido(ValidationError):
    """Dados recusados no controle de relatório."""


def _chave(texto):
    return (texto or '').strip().casefold()


def _proximo_padrao(sequencia):
    return 1540 if sequencia == GRUPO_PADRAO else 1


def sequencias_disponiveis():
    return list(SEQUENCIAS)


def sequencia_valida(codigo):
    return codigo in _SEQUENCIA_POR_CODIGO


def info_sequencia(codigo):
    return _SEQUENCIA_POR_CODIGO.get(
        codigo or GRUPO_PADRAO, _SEQUENCIA_POR_CODIGO[GRUPO_PADRAO])


def nome_especie_processo(processo):
    if processo.especie_fk_id and processo.especie_fk:
        return processo.especie_fk.nome or ''
    return processo.especie or ''


def sequencia_ativa(codigo):
    return codigo in SEQUENCIAS_ATIVAS


def sequencia_do_processo(processo):
    """Código da sequência de numeração conforme a espécie do processo.

    Ordem: ajuste manual no processo → sequência cadastrada na espécie →
    mapa legado pelo nome → Liquidação (demais Liquidações).
    """
    if not especie_gera_relatorio(processo):
        return None
    ajuste = (getattr(processo, 'sequencia_relatorio', None) or '').strip()
    if ajuste and sequencia_ativa(ajuste):
        return ajuste
    especie = processo.especie_fk if getattr(processo, 'especie_fk_id', None) else None
    if especie is not None:
        cadastrada = (especie.sequencia_numeracao or '').strip()
        if cadastrada and sequencia_ativa(cadastrada):
            return cadastrada
    mapeada = _ESPECIE_PARA_SEQUENCIA.get(_chave(nome_especie_processo(processo)))
    if mapeada and sequencia_ativa(mapeada):
        return mapeada
    if processo.genero == perm.GRUPO_LIQUIDACOES:
        return GRUPO_PADRAO
    return None


def estado_sequencia(grupo=GRUPO_PADRAO):
    seq = SequenciaRelatorio.objects.filter(grupo=grupo).first()
    proximo = seq.proximo_numero if seq else _proximo_padrao(grupo)
    return {
        'grupo': grupo,
        'proximo': proximo,
        'ultimo': max(proximo - 1, 0),
        'nome': info_sequencia(grupo)['nome'],
    }


def especie_gera_relatorio(processo):
    especie = processo.especie_fk if processo.especie_fk_id else None
    if especie is not None:
        return bool(especie.gera_relatorio)
    return processo.genero == perm.GRUPO_LIQUIDACOES


def _inteiro(bruto):
    try:
        return int(str(bruto).strip())
    except (TypeError, ValueError):
        return None


def filtro_sequencia(grupo):
    if grupo == GRUPO_PADRAO:
        return Q(sequencia=grupo) | Q(sequencia='', grupo=GRUPO_PADRAO)
    return Q(sequencia=grupo)


def _numeros_reservados(grupo):
    return set(
        ReservaNumeroRelatorio.objects.filter(grupo=grupo, processo__isnull=True)
        .values_list('numero', flat=True)
    )


def reservas_abertas(grupo=GRUPO_PADRAO):
    return (ReservaNumeroRelatorio.objects
            .filter(grupo=grupo, processo__isnull=True)
            .select_related('criado_por')
            .order_by('numero', 'id'))


def contagens_reservas_por_sequencia():
    totais = {item['codigo']: 0 for item in SEQUENCIAS}
    for linha in (ReservaNumeroRelatorio.objects
                  .filter(processo__isnull=True)
                  .values('grupo')
                  .annotate(n=Count('id'))):
        if linha['grupo'] in totais:
            totais[linha['grupo']] += linha['n']
    return totais


def total_reservas_abertas():
    return ReservaNumeroRelatorio.objects.filter(processo__isnull=True).count()


def reservas_abertas_mapa(grupo=GRUPO_PADRAO):
    return {
        str(reserva.numero): reserva.data.isoformat()
        for reserva in reservas_abertas(grupo)
    }


def reserva_do_numero(numero, grupo=GRUPO_PADRAO):
    return (ReservaNumeroRelatorio.objects
            .filter(grupo=grupo, numero=numero, processo__isnull=True)
            .first())


def _liberar_reservas_do_processo(processo):
    ReservaNumeroRelatorio.objects.filter(processo=processo).update(
        processo=None, usado_em=None)


def _consumir_reserva(processo, numero):
    _liberar_reservas_do_processo(processo)
    sequencia = sequencia_do_processo(processo) or GRUPO_PADRAO
    reserva = reserva_do_numero(numero, sequencia)
    if reserva is None:
        return
    reserva.processo = processo
    reserva.usado_em = timezone.now()
    reserva.save(update_fields=['processo', 'usado_em'])


def numeros_usados(grupo, ignorar=None):
    """Números ainda presos nesta sequência (ativos, guardados ou históricos)."""
    ignorar = set(ignorar or ())
    usados = set()
    consulta = (LinhaControleRelatorio.objects
                .filter(filtro_sequencia(grupo))
                .exclude(numero_relatorio='')
                .exclude(situacao_linha=LinhaControleRelatorio.SITUACAO_CANCELADA)
                .filter(
                    Q(situacao_linha__in=[
                        LinhaControleRelatorio.SITUACAO_RESERVADA,
                        LinhaControleRelatorio.SITUACAO_HISTORICA,
                    ])
                    | Q(processo__isnull=False)
                ))
    for bruto in consulta.values_list('numero_relatorio', flat=True):
        numero = _inteiro(bruto)
        if numero:
            usados.add(numero)
    return usados - ignorar


def _consumir_numero_devolvido_hoje(grupo):
    """Menor número verde (RESERVADA) devolvido à fila hoje.

    Consome a linha sob lock para dois "Gerar número" não pegarem o mesmo.
    A data da linha (`data_relatorio`) define o "mesmo dia".
    """
    hoje = timezone.localdate()
    linhas = list(
        LinhaControleRelatorio.objects
        .select_for_update()
        .filter(
            processo__isnull=True,
            situacao_linha=LinhaControleRelatorio.SITUACAO_RESERVADA,
            data_relatorio=hoje,
        )
        .filter(filtro_sequencia(grupo))
        .exclude(numero_relatorio='')
    )
    melhor = None
    melhor_n = None
    for linha in linhas:
        numero = _inteiro(linha.numero_relatorio)
        if numero and (melhor_n is None or numero < melhor_n):
            melhor = linha
            melhor_n = numero
    if melhor is None:
        return None
    # Libera o número; `registrar` cria/atualiza a linha do novo processo.
    melhor.delete()
    return melhor_n


@transaction.atomic
def definir_ultimo_numero(usuario, ultimo, grupo=GRUPO_PADRAO):
    """O próximo relatório será ultimo + 1."""
    perm.assert_permissao(
        perm.pode_definir_ultimo_relatorio(usuario),
        'Somente o administrador define o último número de relatório.')
    if not sequencia_valida(grupo):
        raise RelatorioInvalido('Sequência de relatório inválida.')
    try:
        ultimo = int(str(ultimo).strip())
    except (TypeError, ValueError):
        raise RelatorioInvalido('Informe um número inteiro para o último relatório.')
    if ultimo < 0:
        raise RelatorioInvalido('O último número não pode ser negativo.')

    seq, _ = SequenciaRelatorio.objects.select_for_update().get_or_create(
        grupo=grupo, defaults={'proximo_numero': ultimo + 1})
    seq.proximo_numero = ultimo + 1
    seq.save(update_fields=['proximo_numero'])
    LinhaControleRelatorio.objects.filter(
        processo__isnull=True,
        situacao_linha=LinhaControleRelatorio.SITUACAO_ATIVA,
    ).filter(filtro_sequencia(grupo)).delete()
    return estado_sequencia(grupo)


def proximo_numero(grupo):
    """Trava a sequência para dois salvamentos não saírem iguais.

    Preferência: números devolvidos à fila no mesmo dia (linha verde).
    Fora isso, usa o contador definido pelo administrador. Números
    cancelados (vermelhos) ou verdes de outro dia não entram aqui —
    só por número específico / vínculo no Controle.
    """
    SequenciaRelatorio.objects.get_or_create(
        grupo=grupo, defaults={'proximo_numero': _proximo_padrao(grupo)})
    seq = SequenciaRelatorio.objects.select_for_update().get(grupo=grupo)

    reuso = _consumir_numero_devolvido_hoje(grupo)
    if reuso is not None:
        return str(reuso)

    usados = numeros_usados(grupo) | _numeros_reservados(grupo)

    numero = int(seq.proximo_numero or 1)
    if numero < 1:
        numero = 1
    # Limpa sobras ativas órfãs abaixo do contador; preserva guardadas/canceladas.
    LinhaControleRelatorio.objects.filter(
        processo__isnull=True,
        situacao_linha=LinhaControleRelatorio.SITUACAO_ATIVA,
    ).filter(filtro_sequencia(grupo)).exclude(numero_relatorio='').delete()

    while numero in usados:
        numero += 1
    seq.proximo_numero = numero + 1
    seq.save(update_fields=['proximo_numero'])
    return str(numero)


def _consulta_linha_pre_reservada(processo):
    """Query: mesmo nº de processo na planilha em amarelo (saiu sem relatório).

    Só isso dispara o aviso na análise e o reuso no botão Gerar.
    Histórico normal, verde ou vermelho: Gerar emite o sequencial
    (verde do mesmo dia ainda pode entrar pelo buraco do contador).
    """
    numero = (processo.numero_processo or '').strip()
    if not numero:
        return LinhaControleRelatorio.objects.none()
    sequencia = sequencia_do_processo(processo) or GRUPO_PADRAO
    return (
        LinhaControleRelatorio.objects
        .filter(filtro_sequencia(sequencia))
        .filter(numero_processo__iexact=numero)
        .exclude(numero_relatorio='')
        .filter(sem_relatorio=True)
        .exclude(situacao_linha=LinhaControleRelatorio.SITUACAO_CANCELADA)
        .filter(Q(processo__isnull=True) | Q(processo=processo))
        .order_by('-data_relatorio', '-id')
    )


def _linha_pre_reservada_do_processo(processo):
    """Linha amarela (saiu sem relatório) do mesmo nº de processo."""
    return _consulta_linha_pre_reservada(processo).select_for_update().first()


def aviso_numero_reaproveitavel(processo):
    """Aviso na análise só se a planilha tem o processo em amarelo."""
    if not processo or (processo.numero_relatorio or '').strip():
        return None
    if not especie_gera_relatorio(processo):
        return None
    linha = _consulta_linha_pre_reservada(processo).first()
    if linha is None:
        return None
    situacao = (linha.situacao_linha or '').strip()
    return {
        'numero': (linha.numero_relatorio or '').strip(),
        'data': linha.data_relatorio,
        'situacao': situacao,
        'sem_relatorio': bool(linha.sem_relatorio),
    }


def _remover_linhas_duplicadas_do_numero(numero_txt, sequencia, manter_id):
    """Remove qualquer outra linha do mesmo nº após ativar uma.

    Cobre histórico/reserva/cancelada e ATIVA órfã (sem processo).
    Linhas ATIVAS de outro processo já foram tratadas por
    `_limpar_outros_donos_do_numero`.
    """
    if not numero_txt or manter_id is None:
        return
    outras = list(
        LinhaControleRelatorio.objects
        .filter(filtro_sequencia(sequencia), numero_relatorio=numero_txt)
        .exclude(id=manter_id)
    )
    for linha in outras:
        if (
            linha.situacao_linha == LinhaControleRelatorio.SITUACAO_ATIVA
            and linha.processo_id
        ):
            continue
        linha.delete()


def _buscar_linha_reaproveitavel(sequencia, numero_txt, processo):
    """Linha existente do mesmo nº para virar a ATIVA do processo."""
    if not numero_txt:
        return None
    candidatos = list(
        LinhaControleRelatorio.objects
        .filter(filtro_sequencia(sequencia), numero_relatorio=numero_txt)
        .filter(situacao_linha__in=[
            LinhaControleRelatorio.SITUACAO_RESERVADA,
            LinhaControleRelatorio.SITUACAO_CANCELADA,
            LinhaControleRelatorio.SITUACAO_HISTORICA,
        ])
        .order_by('-atualizado_em', '-id')
    )
    if not candidatos:
        # ATIVA órfã (sem FK) — ex.: import/desvínculo incompleto.
        candidatos = list(
            LinhaControleRelatorio.objects
            .filter(filtro_sequencia(sequencia), numero_relatorio=numero_txt)
            .filter(
                situacao_linha=LinhaControleRelatorio.SITUACAO_ATIVA,
                processo__isnull=True,
            )
            .order_by('-atualizado_em', '-id')
        )
    if not candidatos:
        return None
    num_proc = (processo.numero_processo or '').strip().casefold()
    if num_proc:
        for linha in candidatos:
            if (linha.numero_processo or '').strip().casefold() == num_proc:
                return linha
    return candidatos[0]


def atribuir_se_preciso(processo):
    """Gera o número só se a espécie gera relatório e o processo ainda não tem.

    Não grava o processo: o chamador inclui `numero_relatorio` no save.
    Funciona também com "sem relatório" — o nº e a data são obrigatórios
    para encaminhar ao Controlador.

    Se a planilha já tiver número reservado ou histórico marcado com o
    mesmo nº de processo, reaproveita esse número em vez de emitir um
    sequencial novo.
    """
    if not especie_gera_relatorio(processo):
        return False
    if processo.numero_relatorio:
        registrar(processo)
        return False
    sequencia = sequencia_do_processo(processo)
    if not sequencia:
        return False
    pre = _linha_pre_reservada_do_processo(processo)
    if pre is not None:
        processo.numero_relatorio = (pre.numero_relatorio or '').strip()
        # Data do número reaproveitado (não a data em que o processo foi assumido).
        processo.data_analise = pre.data_relatorio or timezone.localdate()
        registrar(processo)
        return True
    processo.numero_relatorio = proximo_numero(sequencia)
    # Data do número = dia em que foi gerado.
    processo.data_analise = timezone.localdate()
    registrar(processo)
    return True


def _inteiro_atual(processo):
    try:
        return int(str(processo.numero_relatorio).strip())
    except (TypeError, ValueError):
        return None


def registrar(processo):
    """Cria ou atualiza a linha da planilha a partir do processo.

    Se o número informado já existir em uma linha cancelada, reservada ou
    histórica da mesma sequência, essa linha é reaproveitada e volta ao normal.

    Se o número já estiver ATIVO em outro processo, esse processo é
    desvinculado (perde o número) e a linha passa para o processo atual.

    Se o processo trocar de número, o número antigo permanece na planilha:
    verde (mesmo dia, reuso automático) ou vermelho (outro dia, só
    número específico).
    """
    sem_relatorio = bool(getattr(processo, 'sem_relatorio', False))
    if not processo.numero_relatorio and not sem_relatorio:
        return None
    dados = _dados_da_linha(processo)
    dados['sem_relatorio'] = sem_relatorio
    dados['situacao_linha'] = LinhaControleRelatorio.SITUACAO_ATIVA

    numero_txt = str(processo.numero_relatorio or '').strip()
    sequencia = sequencia_do_processo(processo) or GRUPO_PADRAO

    # Número antigo deste processo: não some da planilha.
    antiga = LinhaControleRelatorio.objects.filter(processo=processo).first()
    if (
        antiga is not None
        and numero_txt
        and not sem_relatorio
        and (antiga.numero_relatorio or '').strip()
        and (antiga.numero_relatorio or '').strip() != numero_txt
    ):
        _preservar_numero_apos_troca(antiga)
        antiga = None

    reaproveitar = None
    if numero_txt:
        # Também com "sem relatório": o nº da planilha precisa ser único.
        reaproveitar = _buscar_linha_reaproveitavel(
            sequencia, numero_txt, processo)
        if reaproveitar is None:
            reaproveitar = (
                LinhaControleRelatorio.objects
                .filter(filtro_sequencia(sequencia), numero_relatorio=numero_txt)
                .filter(situacao_linha=LinhaControleRelatorio.SITUACAO_ATIVA)
                .exclude(processo=processo)
                .exclude(processo__isnull=True)
                .order_by('-atualizado_em', '-id')
                .first()
            )
            if reaproveitar is not None:
                _desvincular_processo_do_numero(reaproveitar.processo, numero_txt)

    if reaproveitar is not None:
        antiga = LinhaControleRelatorio.objects.filter(processo=processo).first()
        if antiga is not None and antiga.id != reaproveitar.id:
            # Sem número próprio diferente (já preservado acima) — remove sobra.
            if (
                (antiga.numero_relatorio or '').strip()
                and (antiga.numero_relatorio or '').strip() != numero_txt
            ):
                _preservar_numero_apos_troca(antiga)
            else:
                antiga.delete()
        for campo, valor in dados.items():
            setattr(reaproveitar, campo, valor)
        reaproveitar.processo = processo
        reaproveitar.situacao_linha = LinhaControleRelatorio.SITUACAO_ATIVA
        obs = (reaproveitar.observacao or '').strip()
        if (
            obs.startswith('Relatório cancelado')
            or obs.startswith('Relatório desfeito')
            or obs.startswith('Número liberado')
            or obs.startswith('Número desfeito')
            or 'desvinculado' in obs.casefold()
        ):
            reaproveitar.observacao = processo.observacao or ''
        reaproveitar.save()
        _limpar_outros_donos_do_numero(processo, numero_txt, sequencia)
        _remover_linhas_duplicadas_do_numero(
            numero_txt, sequencia, reaproveitar.id)
        return reaproveitar

    _limpar_outros_donos_do_numero(processo, numero_txt, sequencia)
    linha, _ = LinhaControleRelatorio.objects.update_or_create(
        processo=processo, defaults=dados)
    _remover_linhas_duplicadas_do_numero(numero_txt, sequencia, linha.id)
    return linha


def _data_linha_e_hoje(linha):
    data = getattr(linha, 'data_relatorio', None)
    return bool(data) and data == timezone.localdate()


def _preservar_numero_apos_troca(linha):
    """Ao trocar o nº: verde se a data for hoje (Gerar reusa); senão vermelho."""
    if linha is None:
        return
    numero = (linha.numero_relatorio or '').strip()
    if not numero and not linha.sem_relatorio:
        linha.delete()
        return
    if _data_linha_e_hoje(linha):
        _preservar_numero_devolvido(
            linha,
            observacao=(
                'Número desfeito — disponível para reuso automático no mesmo dia.'
            ),
        )
        return
    _preservar_numero_liberado(linha)


def _preservar_numero_liberado(linha):
    """Mantém número e data na planilha em vermelho (só número específico)."""
    if linha is None:
        return
    numero = (linha.numero_relatorio or '').strip()
    if not numero and not linha.sem_relatorio:
        linha.delete()
        return
    linha.processo = None
    linha.situacao_linha = LinhaControleRelatorio.SITUACAO_CANCELADA
    linha.observacao = (
        'Número liberado — reuso só com número específico na análise.'
    )
    linha.save(update_fields=[
        'processo', 'situacao_linha', 'observacao', 'atualizado_em'])


def _preservar_numero_devolvido(linha, observacao=None):
    """Mantém número e data na planilha (verde) para reuso no mesmo dia."""
    if linha is None:
        return
    numero = (linha.numero_relatorio or '').strip()
    if not numero and not linha.sem_relatorio:
        linha.delete()
        return
    linha.processo = None
    linha.situacao_linha = LinhaControleRelatorio.SITUACAO_RESERVADA
    linha.observacao = observacao or (
        'Número liberado ao voltar à fila — disponível para reuso no mesmo dia.'
    )
    linha.save(update_fields=[
        'processo', 'situacao_linha', 'observacao', 'atualizado_em'])


def liberar_numero_ao_marcar_sem_relatorio(processo):
    """Processo passa a ser sem relatório: o nº antigo fica vermelho na planilha.

    A linha do processo deixa de carregar o número; quem precisar usa o
    número específico depois. O processo fica amarelo sem nº.
    """
    numero = str(processo.numero_relatorio or '').strip()
    if not numero:
        return None
    linha = LinhaControleRelatorio.objects.filter(processo=processo).first()
    if linha is not None and (linha.numero_relatorio or '').strip():
        _preservar_numero_liberado(linha)
    else:
        # Garante o número na planilha mesmo sem linha previa.
        LinhaControleRelatorio.objects.create(
            processo=None,
            numero_processo=processo.numero_processo or '',
            volume=processo.volume or '',
            numero_relatorio=numero,
            sem_relatorio=False,
            situacao_linha=LinhaControleRelatorio.SITUACAO_CANCELADA,
            data_relatorio=processo.data_analise or timezone.localdate(),
            secretaria=processo.secretaria or '',
            contratada=processo.contratada or '',
            objeto=processo.objeto or '',
            valor=processo.valor or '',
            periodo=processo.periodo or '',
            destino=processo.destino or '',
            analista=processo.nome_analista or '',
            status_analise='',
            observacao='Número liberado — disponível para uso com número específico.',
            grupo=processo.genero or '',
            sequencia=sequencia_do_processo(processo) or GRUPO_PADRAO,
        )
    processo.numero_relatorio = None
    processo.save(update_fields=['numero_relatorio'])
    return numero


def _desvincular_processo_do_numero(processo, numero_txt):
    """Tira o número do processo (cadastro), sem apagar a linha da planilha."""
    if processo is None:
        return
    campos = []
    atual = str(processo.numero_relatorio or '').strip()
    if atual and atual == str(numero_txt).strip():
        processo.numero_relatorio = None
        campos.append('numero_relatorio')
    if campos:
        processo.save(update_fields=campos)


def _limpar_outros_donos_do_numero(processo, numero_txt, sequencia):
    """Garante que nenhum outro processo/linha ATIVA fique com o mesmo número."""
    if not numero_txt:
        return []
    liberados = []
    outras = list(
        LinhaControleRelatorio.objects
        .filter(filtro_sequencia(sequencia), numero_relatorio=numero_txt)
        .filter(situacao_linha=LinhaControleRelatorio.SITUACAO_ATIVA)
        .exclude(processo=processo)
        .exclude(processo__isnull=True)
    )
    for linha in outras:
        outro = linha.processo
        if outro is not None:
            liberados.append(outro.numero_processo or str(outro.id))
            _desvincular_processo_do_numero(outro, numero_txt)
        linha.delete()
    # Cadastros órfãos (número no processo sem linha ATIVA nesta sequência).
    for outro in (Processo.objects
                  .filter(numero_relatorio=numero_txt)
                  .exclude(id=processo.id)):
        if sequencia_do_processo(outro) == sequencia:
            liberados.append(outro.numero_processo or str(outro.id))
            _desvincular_processo_do_numero(outro, numero_txt)
    return liberados


@transaction.atomic
def alterar_numero(usuario, processo_id, novo, data=None):
    """Analista do grupo ou administrador grava o número e a data do relatório.

    Se o número já estiver ativo em outro processo da mesma sequência, esse
    processo é desvinculado automaticamente.
    """
    processo = (Processo.objects.select_for_update()
                .filter(id=processo_id).first())
    if processo is None:
        raise RelatorioInvalido('Processo não encontrado.')
    perm.assert_permissao(
        perm.pode_editar_numero_relatorio(usuario, processo),
        'Somente o analista do grupo e o administrador alteram o número.')
    if not especie_gera_relatorio(processo):
        raise RelatorioInvalido('Esta espécie não gera número de relatório.')
    limpar_sem_relatorio = bool(processo.sem_relatorio)
    if limpar_sem_relatorio:
        processo.sem_relatorio = False
    sequencia = sequencia_do_processo(processo) or GRUPO_PADRAO
    try:
        novo = int(str(novo).strip())
    except (TypeError, ValueError):
        raise RelatorioInvalido('Informe um número inteiro para o relatório.')
    if novo < 1:
        raise RelatorioInvalido('O número do relatório deve ser maior que zero.')
    try:
        data_analise = converter_data(data)
    except ValidationError as exc:
        raise RelatorioInvalido('; '.join(exc.messages))
    if data_analise is None:
        reserva = reserva_do_numero(novo, sequencia)
        if reserva is not None:
            data_analise = reserva.data
    if data_analise is None:
        raise RelatorioInvalido(
            'Informe a data deste número de relatório.')

    # Quem já usa este número (para avisar depois do desvínculo).
    numero_txt = str(novo)
    donos_anteriores = list(
        LinhaControleRelatorio.objects
        .filter(filtro_sequencia(sequencia), numero_relatorio=numero_txt)
        .filter(situacao_linha=LinhaControleRelatorio.SITUACAO_ATIVA)
        .exclude(processo=processo)
        .exclude(processo__isnull=True)
        .values_list('numero_processo', flat=True)
    )

    atual = _inteiro_atual(processo)
    campos = []
    if limpar_sem_relatorio:
        campos.append('sem_relatorio')
    anterior_numero = processo.numero_relatorio or ''
    if atual != novo:
        processo.numero_relatorio = str(novo)
        campos.append('numero_relatorio')
        seq, _ = SequenciaRelatorio.objects.select_for_update().get_or_create(
            grupo=sequencia,
            defaults={'proximo_numero': novo + 1})
        if int(seq.proximo_numero or 0) <= novo:
            seq.proximo_numero = novo + 1
            seq.save(update_fields=['proximo_numero'])
        registrar_diff(
            processo, 'numero_relatorio', anterior_numero, str(novo), usuario)

    if processo.data_analise != data_analise:
        anterior_data = (
            processo.data_analise.isoformat() if processo.data_analise else '')
        processo.data_analise = data_analise
        campos.append('data_analise')
        registrar_diff(
            processo, 'data_analise', anterior_data,
            data_analise.isoformat(), usuario)

    if campos:
        processo.save(update_fields=campos)
        registrar(processo)
    else:
        registrar(processo)
    _consumir_reserva(processo, novo)
    processo._numeros_desvinculados = [
        n for n in donos_anteriores if n]
    return processo


@transaction.atomic
def alterar_sequencia(usuario, processo_id, nova_sequencia):
    """Administrador troca o grupo de numeração do processo.

    O número antigo fica livre na sequência de origem. Se o processo já
    tinha relatório, recebe o próximo número do grupo novo.
    """
    processo = (Processo.objects.select_for_update()
                .filter(id=processo_id).first())
    if processo is None:
        raise RelatorioInvalido('Processo não encontrado.')
    perm.assert_permissao(
        perm.pode_alterar_sequencia_relatorio(usuario),
        'Somente o administrador troca o grupo de numeração.')
    if not especie_gera_relatorio(processo):
        raise RelatorioInvalido('Esta espécie não gera número de relatório.')

    nova = (nova_sequencia or '').strip()
    if nova and not sequencia_ativa(nova):
        raise RelatorioInvalido('Escolha um grupo de numeração válido.')

    anterior = sequencia_do_processo(processo) or GRUPO_PADRAO
    anterior_nome = info_sequencia(anterior)['nome']
    anterior_numero = processo.numero_relatorio or ''

    processo.sequencia_relatorio = nova
    processo.save(update_fields=['sequencia_relatorio'])
    destino = sequencia_do_processo(processo) or GRUPO_PADRAO
    destino_nome = info_sequencia(destino)['nome']

    if destino == anterior:
        registrar(processo)
        return processo

    _liberar_reservas_do_processo(processo)
    if processo.numero_relatorio and not processo.sem_relatorio:
        processo.numero_relatorio = None
        processo.save(update_fields=['numero_relatorio'])
        processo.numero_relatorio = proximo_numero(destino)
        processo.save(update_fields=['numero_relatorio'])
        registrar_diff(
            processo, 'numero_relatorio', anterior_numero,
            processo.numero_relatorio or '', usuario)

    registrar(processo)
    registrar_diff(
        processo, 'sequencia_relatorio', anterior_nome, destino_nome, usuario)
    return processo


@transaction.atomic
def editar_linha(usuario, linha_id, dados):
    """Edita os dados da linha direto no Controle de relatório."""
    perm.assert_permissao(
        perm.pode_cancelar_linha_relatorio(usuario),
        'Somente analista de Liquidações, a Gestão e o administrador '
        'editam linha no Controle de relatório.')
    linha = (LinhaControleRelatorio.objects
             .select_for_update()
             .filter(id=linha_id)
             .first())
    if linha is None:
        raise RelatorioInvalido('Linha não encontrada.')
    if not (linha.numero_relatorio or '').strip() and not linha.sem_relatorio:
        raise RelatorioInvalido('Esta linha não tem número de relatório.')

    try:
        data = converter_data(dados.get('data_relatorio'))
    except ValidationError as exc:
        raise RelatorioInvalido('; '.join(exc.messages))
    if data is None:
        raise RelatorioInvalido('Informe a data do relatório.')

    novo_numero = _numero_relatorio_celula(dados.get('numero_relatorio'))
    if not novo_numero:
        raise RelatorioInvalido('Informe o número do relatório.')

    grupo = (linha.sequencia or '').strip() or GRUPO_PADRAO
    anterior_numero = (linha.numero_relatorio or '').strip()
    if novo_numero != anterior_numero:
        if linha.situacao_linha == LinhaControleRelatorio.SITUACAO_CANCELADA:
            raise RelatorioInvalido(
                'Não é possível trocar o número de uma linha cancelada.')
        conflito = (
            LinhaControleRelatorio.objects
            .select_for_update()
            .filter(filtro_sequencia(grupo), numero_relatorio=novo_numero)
            .exclude(pk=linha.pk)
            .exclude(situacao_linha=LinhaControleRelatorio.SITUACAO_CANCELADA)
            .exists()
        )
        if conflito:
            raise RelatorioInvalido(
                f'O número {novo_numero} já está em uso neste grupo.')

    valor_bruto = dados.get('valor')
    if valor_bruto in (None, ''):
        valor = ''
    else:
        valor = formatar_valor(valor_bruto)

    # Troca de nº na planilha: o antigo fica verde (hoje) ou vermelho (outro dia).
    if novo_numero != anterior_numero and anterior_numero:
        liberada = LinhaControleRelatorio.objects.create(
            processo=None,
            numero_relatorio=anterior_numero,
            data_relatorio=linha.data_relatorio,
            numero_processo=linha.numero_processo or '',
            volume=linha.volume or '',
            secretaria=linha.secretaria or '',
            contratada=linha.contratada or '',
            objeto=linha.objeto or '',
            valor=linha.valor or '',
            periodo=linha.periodo or '',
            destino=linha.destino or '',
            analista=linha.analista or '',
            status_analise=linha.status_analise or '',
            observacao='',
            sem_relatorio=False,
            situacao_linha=LinhaControleRelatorio.SITUACAO_ATIVA,
            grupo=linha.grupo or grupo,
            sequencia=grupo,
        )
        _preservar_numero_apos_troca(liberada)

    linha.numero_relatorio = novo_numero
    linha.data_relatorio = data
    linha.numero_processo = str(dados.get('numero_processo') or '').strip()[:255]
    linha.secretaria = str(dados.get('secretaria') or '').strip()[:255]
    linha.contratada = str(dados.get('contratada') or '').strip()[:255]
    linha.objeto = str(dados.get('objeto') or '').strip()
    linha.valor = valor[:255]
    linha.periodo = str(dados.get('periodo') or '').strip()[:255]
    linha.destino = str(dados.get('destino') or '').strip()[:255]
    linha.analista = str(dados.get('analista') or '').strip()[:255]
    linha.observacao = str(dados.get('observacao') or '').strip()
    linha.volume = str(dados.get('volume') or '').strip()[:255]
    linha.sem_relatorio = str(dados.get('sem_relatorio') or '') in (
        '1', 'true', 'True', 'on', 'sim')
    linha.save()

    if novo_numero != anterior_numero:
        numero_int = _inteiro(novo_numero)
        if numero_int:
            _atualizar_proximo_numero_grupo(grupo, numero_int)
            reserva = reserva_do_numero(numero_int, grupo)
            if reserva is not None:
                reserva.delete()

    processo = linha.processo
    if processo is not None:
        campos = []
        if (processo.numero_relatorio or '').strip() != novo_numero:
            processo.numero_relatorio = novo_numero
            campos.append('numero_relatorio')
        if processo.data_analise != data:
            processo.data_analise = data
            campos.append('data_analise')
        if bool(processo.sem_relatorio) != linha.sem_relatorio:
            processo.sem_relatorio = linha.sem_relatorio
            campos.append('sem_relatorio')
        if campos:
            processo.save(update_fields=campos)
    return linha


@transaction.atomic
def alternar_sem_relatorio(usuario, linha_id):
    """Marca/desmarca \"sem relatório\" (amarelo) direto na planilha."""
    perm.assert_permissao(
        perm.pode_cancelar_linha_relatorio(usuario),
        'Somente analista de Liquidações, a Gestão e o administrador '
        'alteram \"sem relatório\" no Controle.')
    linha = (LinhaControleRelatorio.objects
             .select_for_update()
             .filter(id=linha_id)
             .first())
    if linha is None:
        raise RelatorioInvalido('Linha não encontrada.')
    if linha.situacao_linha not in (
            LinhaControleRelatorio.SITUACAO_ATIVA,
            LinhaControleRelatorio.SITUACAO_HISTORICA):
        raise RelatorioInvalido(
            'Só é possível marcar sem relatório em linha ativa ou histórica.')
    if not (linha.numero_relatorio or '').strip():
        raise RelatorioInvalido('Esta linha não tem número de relatório.')

    novo = not bool(linha.sem_relatorio)
    linha.sem_relatorio = novo
    obs = (linha.observacao or '').strip()
    marca = 'Sem relatório'
    if novo:
        if marca.casefold() not in obs.casefold():
            linha.observacao = f'{obs} · {marca}'.strip(' ·') if obs else marca
    else:
        # Remove marca simples deixada por esta ação.
        partes = [
            p.strip() for p in obs.replace('·', '|').split('|')
            if p.strip() and p.strip().casefold() != marca.casefold()
        ]
        linha.observacao = ' · '.join(partes)
    linha.save(update_fields=[
        'sem_relatorio', 'observacao', 'atualizado_em'])

    processo = linha.processo
    if processo is not None and bool(processo.sem_relatorio) != novo:
        processo.sem_relatorio = novo
        processo.save(update_fields=['sem_relatorio'])
    return linha


def _desligar_processo_da_linha(linha):
    """Tira o nº do processo ligado à linha (se houver)."""
    processo = linha.processo
    if processo is None:
        return
    campos = []
    if processo.numero_relatorio:
        processo.numero_relatorio = None
        campos.append('numero_relatorio')
    if getattr(processo, 'sem_relatorio', False):
        processo.sem_relatorio = False
        campos.append('sem_relatorio')
    if campos:
        processo.save(update_fields=campos)
    _liberar_reservas_do_processo(processo)


@transaction.atomic
def desfazer_linha(usuario, linha_id):
    """Desfaz o relatório na planilha (⋮ → Desfazer).

    - Mesmo dia da data do relatório → verde (RESERVADA), reuso automático.
    - Dia diferente → vermelho (CANCELADA), reuso só com nº específico.
    """
    perm.assert_permissao(
        perm.pode_cancelar_linha_relatorio(usuario),
        'Somente analista de Liquidações, a Gestão e o administrador '
        'desfazem linha no Controle de relatório.')
    linha = (LinhaControleRelatorio.objects
             .select_for_update()
             .filter(id=linha_id)
             .first())
    if linha is None:
        raise RelatorioInvalido('Linha não encontrada.')
    if linha.situacao_linha == LinhaControleRelatorio.SITUACAO_RESERVADA:
        raise RelatorioInvalido('Esta linha já está disponível para reuso.')
    if linha.situacao_linha == LinhaControleRelatorio.SITUACAO_CANCELADA:
        raise RelatorioInvalido(
            'Linha cancelada. Para reutilizar, informe o número específico '
            'na análise ou vincule o processo.')
    if not linha.numero_relatorio and not linha.sem_relatorio:
        raise RelatorioInvalido('Não há número de relatório nesta linha.')

    _desligar_processo_da_linha(linha)
    if _data_linha_e_hoje(linha):
        _preservar_numero_devolvido(
            linha,
            observacao=(
                'Relatório desfeito — disponível para reuso automático '
                'no mesmo dia.'
            ),
        )
    else:
        linha.processo = None
        linha.situacao_linha = LinhaControleRelatorio.SITUACAO_CANCELADA
        linha.observacao = (
            'Relatório desfeito em data anterior — cancelado (vermelho); '
            'reuso só com número específico na análise.'
        )
        linha.save(update_fields=[
            'processo', 'situacao_linha', 'observacao', 'atualizado_em'])
    return linha


@transaction.atomic
def cancelar_linha(usuario, linha_id, destino_numero=None):
    """Cancela a linha na planilha (vermelha), mantendo número e data.

    O número NÃO entra no Gerar automático — só por número específico
    na análise ou vínculo na planilha. Para reuso no mesmo dia, use Desfazer.
    """
    perm.assert_permissao(
        perm.pode_cancelar_linha_relatorio(usuario),
        'Somente analista de Liquidações, a Gestão e o administrador '
        'cancelam linha no Controle de relatório.')
    # Não usar select_related('processo'): o FK é nullable e o PostgreSQL
    # rejeita FOR UPDATE no lado nullable de um OUTER JOIN.
    linha = (LinhaControleRelatorio.objects
             .select_for_update()
             .filter(id=linha_id)
             .first())
    if linha is None:
        raise RelatorioInvalido('Linha não encontrada.')
    if linha.situacao_linha == LinhaControleRelatorio.SITUACAO_CANCELADA:
        raise RelatorioInvalido('Esta linha já foi cancelada.')
    if not linha.numero_relatorio and not linha.sem_relatorio:
        raise RelatorioInvalido('Não há número de relatório nesta linha.')

    _desligar_processo_da_linha(linha)
    linha.processo = None
    linha.situacao_linha = LinhaControleRelatorio.SITUACAO_CANCELADA
    linha.observacao = (
        'Relatório cancelado — reuso só com número específico na análise.'
    )
    linha.save(update_fields=[
        'processo', 'situacao_linha', 'observacao', 'atualizado_em'])
    return linha


def _ultima_passagem_processo(numero_processo):
    """Último registro do processo no sistema (ativo, finalizado ou não)."""
    numero = (numero_processo or '').strip()
    if not numero:
        return None
    return (Processo.objects
            .filter(numero_processo__iexact=numero)
            .order_by('-id')
            .first())


def _preencher_linha_pela_passagem(linha, processo):
    """Copia dados da passagem do processo para a linha da planilha."""
    linha.numero_processo = processo.numero_processo or ''
    linha.volume = processo.volume or ''
    linha.secretaria = processo.secretaria or ''
    linha.contratada = processo.contratada or ''
    linha.objeto = processo.objeto or ''
    linha.valor = processo.valor or ''
    linha.periodo = processo.periodo or ''
    linha.destino = processo.destino or ''
    if processo.nome_analista:
        linha.analista = processo.nome_analista
    if processo.genero:
        linha.grupo = processo.genero


def _sincronizar_processo_pela_importacao(processo, dados):
    """Espelha no processo os campos corrigidos pela planilha Excel.

    Não altera ``numero_processo`` (identidade do cadastro) nem o nº de
    relatório — só texto de planilha (valor, objeto, secretaria…).
    """
    if processo is None:
        return
    pares = (
        ('secretaria', 'secretaria'),
        ('contratada', 'contratada'),
        ('objeto', 'objeto'),
        ('valor', 'valor'),
        ('periodo', 'periodo'),
        ('destino', 'destino'),
        ('volume', 'volume'),
        ('observacao', 'observacao'),
    )
    campos = []
    for campo_proc, campo_dados in pares:
        novo = dados.get(campo_dados)
        if novo is None:
            continue
        novo = str(novo).strip()
        if campo_proc in ('secretaria', 'contratada', 'valor',
                          'periodo', 'destino', 'volume'):
            novo = novo[:255]
        if (getattr(processo, campo_proc, None) or '') == novo:
            continue
        setattr(processo, campo_proc, novo)
        campos.append(campo_proc)
    # nome_analista é property (sem setter) — fica só na linha da planilha.
    data = dados.get('data_relatorio')
    if data and processo.data_analise != data:
        processo.data_analise = data
        campos.append('data_analise')
    if campos:
        processo.save(update_fields=campos)


def _processo_ativo_para_vincular(processo):
    """Só vincula de verdade (FK + nº no cadastro) se o processo ainda tramita."""
    if processo is None:
        return False
    if processo.cancelado_em is not None:
        return False
    if processo.data_saida is not None:
        return False
    if processo.situacao_tramite not in Processo.SITUACOES_ATIVAS:
        return False
    return especie_gera_relatorio(processo)


@transaction.atomic
def vincular_processo_linha(usuario, linha_id, numero_processo):
    """Informa o nº do processo na linha e preenche com a última passagem.

    - Processo ativo: liga de verdade (número no cadastro + linha ativa).
    - Processo finalizado/inativo ou só o número: preenche a planilha e
      mantém a linha histórica, sem exigir tramitação aberta.
    """
    perm.assert_permissao(
        perm.pode_cancelar_linha_relatorio(usuario),
        'Somente analista de Liquidações, a Gestão e o administrador '
        'vinculam processo na planilha.')
    linha = (LinhaControleRelatorio.objects
             .select_for_update()
             .filter(id=linha_id)
             .first())
    if linha is None:
        raise RelatorioInvalido('Linha não encontrada.')
    if linha.situacao_linha not in (
            LinhaControleRelatorio.SITUACAO_CANCELADA,
            LinhaControleRelatorio.SITUACAO_RESERVADA,
            LinhaControleRelatorio.SITUACAO_HISTORICA):
        raise RelatorioInvalido(
            'Só é possível vincular processo a número cancelado, '
            'guardado ou histórico.')
    numero_txt = (linha.numero_relatorio or '').strip()
    if not numero_txt:
        raise RelatorioInvalido('Esta linha não tem número de relatório.')

    numero = (numero_processo or '').strip()
    if not numero:
        raise RelatorioInvalido('Informe o número do processo.')

    processo = _ultima_passagem_processo(numero)
    linha.numero_processo = numero

    if processo is not None:
        _preencher_linha_pela_passagem(linha, processo)
    else:
        # Sem cadastro: ainda grava o número digitado; tenta reaproveitar
        # dados de outra linha da planilha com o mesmo processo.
        outra = (
            LinhaControleRelatorio.objects
            .filter(numero_processo__iexact=numero)
            .exclude(id=linha.id)
            .order_by('-data_relatorio', '-id')
            .first()
        )
        if outra is not None:
            linha.volume = outra.volume or linha.volume
            linha.secretaria = outra.secretaria or linha.secretaria
            linha.contratada = outra.contratada or linha.contratada
            linha.objeto = outra.objeto or linha.objeto
            linha.valor = outra.valor or linha.valor
            linha.periodo = outra.periodo or linha.periodo
            linha.destino = outra.destino or linha.destino
            if outra.analista:
                linha.analista = outra.analista

    if _processo_ativo_para_vincular(processo):
        grupo = (linha.sequencia or '').strip() or GRUPO_PADRAO
        sequencia = sequencia_do_processo(processo) or GRUPO_PADRAO
        if sequencia != grupo:
            nome = info_sequencia(sequencia)['nome']
            raise RelatorioInvalido(
                f'O processo {numero} pertence à sequência {nome}, '
                f'não a {info_sequencia(grupo)["nome"]}.')
        if (
            processo.numero_relatorio
            and not processo.sem_relatorio
            and str(processo.numero_relatorio).strip() == numero_txt
            and LinhaControleRelatorio.objects.filter(
                processo=processo, numero_relatorio=numero_txt,
                situacao_linha=LinhaControleRelatorio.SITUACAO_ATIVA).exists()
        ):
            raise RelatorioInvalido(
                f'O processo {numero} já está vinculado a este número.')

        data = linha.data_relatorio or timezone.localdate()
        campos = []
        if processo.sem_relatorio:
            processo.sem_relatorio = False
            campos.append('sem_relatorio')
        if str(processo.numero_relatorio or '').strip() != numero_txt:
            processo.numero_relatorio = numero_txt
            campos.append('numero_relatorio')
        if processo.data_analise != data:
            processo.data_analise = data
            campos.append('data_analise')
        if campos:
            processo.save(update_fields=campos)
        registrar(processo)
        linha.refresh_from_db()
        return linha

    # Inativo / finalizado / só número: preenche a planilha, sem FK.
    linha.processo = None
    if linha.situacao_linha == LinhaControleRelatorio.SITUACAO_CANCELADA:
        linha.situacao_linha = LinhaControleRelatorio.SITUACAO_HISTORICA
    linha.save()
    return linha


@transaction.atomic
def desvincular_processo_linha(usuario, linha_id):
    """Tira o processo do número de relatório, mantendo a linha na planilha.

    Diferente de cancelar: o número não fica vermelho para reuso automático;
    a linha vira histórica com os dados, e o processo perde o nº no cadastro.
    """
    perm.assert_permissao(
        perm.pode_cancelar_linha_relatorio(usuario),
        'Somente analista de Liquidações, a Gestão e o administrador '
        'desvinculam processo no Controle de relatório.')
    linha = (LinhaControleRelatorio.objects
             .select_for_update()
             .filter(id=linha_id)
             .first())
    if linha is None:
        raise RelatorioInvalido('Linha não encontrada.')
    numero_txt = (linha.numero_relatorio or '').strip()
    if not numero_txt:
        raise RelatorioInvalido('Esta linha não tem número de relatório.')
    tem_vinculo = bool(linha.processo_id) or bool(
        (linha.numero_processo or '').strip())
    if not tem_vinculo:
        raise RelatorioInvalido(
            'Esta linha não tem processo vinculado para desvincular.')

    processo = linha.processo
    if processo is not None:
        campos = []
        if str(processo.numero_relatorio or '').strip() == numero_txt:
            processo.numero_relatorio = None
            campos.append('numero_relatorio')
        if campos:
            processo.save(update_fields=campos)
        _liberar_reservas_do_processo(processo)

    linha.processo = None
    if linha.situacao_linha == LinhaControleRelatorio.SITUACAO_ATIVA:
        linha.situacao_linha = LinhaControleRelatorio.SITUACAO_HISTORICA
    obs = (linha.observacao or '').strip()
    marca = 'Processo desvinculado'
    if marca.casefold() not in obs.casefold():
        linha.observacao = f'{obs} · {marca}'.strip(' ·') if obs else marca
    linha.save(update_fields=[
        'processo', 'situacao_linha', 'observacao', 'atualizado_em'])
    # Mantém numero_processo e demais dados como histórico na planilha.
    return linha


@transaction.atomic
def apagar_linha(usuario, linha_id):
    """Remove a linha do Controle de verdade — some da planilha.

    Só o administrador. Se estiver ligada a um processo, limpa o número
    nele. Se era o último número emitido da sequência, o contador volta.
    """
    perm.assert_permissao(
        perm.pode_apagar_linha_relatorio(usuario),
        'Somente o administrador apaga linha do Controle de relatório.')
    linha = (LinhaControleRelatorio.objects
             .select_for_update()
             .filter(id=linha_id)
             .first())
    if linha is None:
        raise RelatorioInvalido('Linha não encontrada.')

    numero_txt = (linha.numero_relatorio or '').strip()
    sequencia = (linha.sequencia or '').strip() or GRUPO_PADRAO
    numero = _inteiro(numero_txt)
    processo = linha.processo

    if processo is not None:
        campos = []
        if processo.numero_relatorio:
            processo.numero_relatorio = None
            campos.append('numero_relatorio')
        if getattr(processo, 'sem_relatorio', False):
            processo.sem_relatorio = False
            campos.append('sem_relatorio')
        if campos:
            processo.save(update_fields=campos)
        _liberar_reservas_do_processo(processo)

    if numero and linha.situacao_linha != LinhaControleRelatorio.SITUACAO_CANCELADA:
        seq = (SequenciaRelatorio.objects
               .select_for_update()
               .filter(grupo=sequencia)
               .first())
        if seq and int(seq.proximo_numero or 0) == numero + 1:
            seq.proximo_numero = numero
            seq.save(update_fields=['proximo_numero'])

    linha.delete()
    return {
        'numero_relatorio': numero_txt,
        'sequencia': sequencia,
        'numero_processo': (processo.numero_processo
                            if processo is not None else ''),
    }


@transaction.atomic
def remover_do_processo(processo, *, preservar_numero=False):
    """Desvincula a linha do processo.

    Por padrão (declinar / voltar à fila): a linha fica verde (RESERVADA)
    com número e data. No mesmo dia, o próximo "Gerar número" reaproveita
    esse número; depois disso, só por vínculo / número específico.

    Com preservar_numero=True (excluir processo): a linha fica vermelha e o
    número permanece disponível para vínculo no Controle.
    """
    linhas = list(LinhaControleRelatorio.objects.filter(processo=processo))
    for linha in linhas:
        if (
            linha.situacao_linha == LinhaControleRelatorio.SITUACAO_ATIVA
            and (linha.numero_relatorio or '').strip()
        ):
            if preservar_numero:
                _preservar_numero_liberado(linha)
            else:
                _preservar_numero_devolvido(linha)
            continue
        if linha.situacao_linha != LinhaControleRelatorio.SITUACAO_ATIVA:
            linha.delete()
            continue
        # ATIVA sem número (ex.: sem relatório) — remove da planilha.
        linha.delete()
    _liberar_reservas_do_processo(processo)


def filtrar_por_termo(consulta, termo):
    """Busca livre em qualquer coluna da planilha de análises."""
    termo = (termo or '').strip()
    if not termo:
        return consulta

    from ..models import Processo
    from datetime import datetime

    filtro = (
        Q(numero_processo__icontains=termo) |
        Q(numero_relatorio__icontains=termo) |
        Q(volume__icontains=termo) |
        Q(secretaria__icontains=termo) |
        Q(contratada__icontains=termo) |
        Q(objeto__icontains=termo) |
        Q(valor__icontains=termo) |
        Q(periodo__icontains=termo) |
        Q(destino__icontains=termo) |
        Q(analista__icontains=termo) |
        Q(status_analise__icontains=termo) |
        Q(observacao__icontains=termo) |
        Q(grupo__icontains=termo) |
        Q(sequencia__icontains=termo) |
        Q(processo__especie__icontains=termo) |
        Q(processo__genero__icontains=termo) |
        Q(processo__objeto__icontains=termo) |
        Q(processo__contratada__icontains=termo) |
        Q(processo__secretaria__icontains=termo) |
        Q(processo__destino__icontains=termo)
    )

    chave = termo.casefold()
    status_codes = [
        codigo for codigo, rotulo in Processo.STATUS_ANALISE_CHOICES
        if chave in rotulo.casefold() or chave in codigo.casefold()
    ]
    if status_codes:
        filtro |= Q(status_analise__in=status_codes)

    for item in SEQUENCIAS:
        if (chave in item['nome'].casefold()
                or chave in item['codigo'].casefold()):
            filtro |= Q(sequencia=item['codigo']) | Q(grupo=item['codigo'])

    if chave in ('sem relatório', 'sem relatorio', 's/r', 'sem n'):
        filtro |= Q(sem_relatorio=True)

    for formato in ('%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y', '%d/%m/%y'):
        try:
            filtro |= Q(data_relatorio=datetime.strptime(termo, formato).date())
            break
        except ValueError:
            continue

    return consulta.filter(filtro)


def listar(usuario, sequencia=None):
    consulta = (LinhaControleRelatorio.objects
                .filter(
                    Q(processo__isnull=False)
                    | Q(situacao_linha__in=[
                        LinhaControleRelatorio.SITUACAO_RESERVADA,
                        LinhaControleRelatorio.SITUACAO_CANCELADA,
                        LinhaControleRelatorio.SITUACAO_HISTORICA,
                    ])
                )
                .select_related('processo'))
    if perm.eh_administrador(usuario) or perm.is_gestao(usuario):
        pass
    elif perm.is_analista(usuario):
        grupo = perm.grupo_do_analista(usuario)
        if grupo == GRUPO_PADRAO:
            # Liquidações vê toda a planilha (todas as sequências).
            # Inclui histórico antigo importado com grupo vazio.
            consulta = consulta.filter(
                Q(grupo=GRUPO_PADRAO)
                | Q(grupo='')
                | Q(sequencia__in=SEQUENCIAS_ATIVAS)
            )
        elif grupo:
            consulta = consulta.filter(grupo=grupo)
        else:
            return consulta.none()
    else:
        return consulta.none()
    if sequencia:
        consulta = consulta.filter(filtro_sequencia(sequencia))
    # Só faz cast quando o nº é inteiro puro. No PostgreSQL,
    # Cast("56 A") quebra a tela inteira (DataError).
    return consulta.annotate(
        numero_ordem=Case(
            When(numero_relatorio='', then=Value(None)),
            When(
                numero_relatorio__regex=r'^[0-9]+$',
                then=Cast('numero_relatorio', IntegerField()),
            ),
            default=Value(None),
            output_field=IntegerField(null=True),
        )
    # Mais recentes primeiro: evita ir até a última página da planilha.
    ).order_by(F('numero_ordem').desc(nulls_last=True), '-numero_relatorio', '-id')


def contagens_por_sequencia(usuario):
    base = listar(usuario)
    totais = {item['codigo']: 0 for item in SEQUENCIAS}
    for linha in base.values('sequencia', 'grupo').annotate(n=Count('id')):
        codigo = linha['sequencia'] or (
            GRUPO_PADRAO if linha['grupo'] == GRUPO_PADRAO else '')
        if codigo in totais:
            totais[codigo] += linha['n']
    return totais


def _dados_da_linha(processo):
    data = processo.data_analise or timezone.localdate()
    sequencia = sequencia_do_processo(processo) or GRUPO_PADRAO
    numero_processo = processo.numero_processo or ''
    volume = processo.volume or ''
    # Bolsa/Auxílio na planilha: concessão = nº do processo; prestação = campo opcional.
    if sequencia in ('BOLSA_ATLETA', 'AUXILIO_COMPETICAO'):
        volume = (processo.numero_processo or '').strip()
        numero_processo = (
            getattr(processo, 'processo_prestacao', None) or ''
        ).strip()
    return {
        'numero_processo': numero_processo,
        'volume': volume,
        'numero_relatorio': processo.numero_relatorio or '',
        'sem_relatorio': bool(getattr(processo, 'sem_relatorio', False)),
        'data_relatorio': data,
        'secretaria': processo.secretaria or '',
        'contratada': processo.contratada or '',
        'objeto': processo.objeto or '',
        'valor': processo.valor or '',
        'periodo': processo.periodo or '',
        'destino': processo.destino or '',
        'analista': processo.nome_analista or '',
        'status_analise': processo.status_analise or '',
        'observacao': processo.observacao or '',
        'grupo': processo.genero or '',
        'sequencia': sequencia,
    }


@transaction.atomic
def destinar_numeros(usuario, inicio=None, fim=None, data=None, grupo=GRUPO_PADRAO,
                     numeros_processo=None, quantidade_auto=None, pares=None):
    """Reserva um número por processo e vincula (linha amarela no Controle).

    Preferencial: `pares` = [(nº processo, nº relatório), ...].
    Legado: faixa inicio/fim ou quantidade_auto + lista de processos.
    """
    perm.assert_permissao(
        perm.pode_destinar_numeros_relatorio(usuario),
        'Somente analista de Liquidações e o administrador destinam números.')
    if not sequencia_valida(grupo):
        raise RelatorioInvalido('Sequência de relatório inválida.')

    try:
        data_reserva = converter_data(data)
    except ValidationError as exc:
        raise RelatorioInvalido('; '.join(exc.messages))
    if data_reserva is None:
        raise RelatorioInvalido('Informe a data desses números.')

    ocupados = numeros_usados(grupo) | _numeros_reservados(grupo)

    if pares is not None:
        numeros, processos_txt = _normalizar_pares(pares)
    elif quantidade_auto not in (None, ''):
        processos_txt = _parse_numeros_processo(numeros_processo)
        if not processos_txt:
            raise RelatorioInvalido('Informe ao menos um processo.')
        numeros = sugerir_numeros_disponiveis(
            grupo, len(processos_txt), ocupados)
    else:
        processos_txt = _parse_numeros_processo(numeros_processo)
        try:
            inicio = int(str(inicio).strip())
            fim = int(str(fim).strip())
        except (TypeError, ValueError):
            raise RelatorioInvalido(
                'Informe o número de relatório de cada processo.')
        if inicio < 1 or fim < 1:
            raise RelatorioInvalido('Os números devem ser maiores que zero.')
        if fim < inicio:
            inicio, fim = fim, inicio
        numeros = list(range(inicio, fim + 1))
        if len(processos_txt) != len(numeros):
            raise RelatorioInvalido(
                f'Informe {len(numeros)} processo'
                f'{"s" if len(numeros) != 1 else ""} '
                f'(um para cada número de {numeros[0]} a {numeros[-1]}).')

    if not numeros:
        raise RelatorioInvalido('Adicione ao menos um processo com número.')
    if len(numeros) > LIMITE_DESTINO:
        raise RelatorioInvalido(
            f'Destine no máximo {LIMITE_DESTINO} números por vez.')
    if len(processos_txt) != len(numeros):
        raise RelatorioInvalido(
            'Cada processo precisa de um número de relatório.')

    choque = [n for n in numeros if n in ocupados]
    if choque:
        if len(choque) == 1:
            raise RelatorioInvalido(f'O número {choque[0]} já está em uso.')
        amostra = ', '.join(str(n) for n in choque[:8])
        extra = '…' if len(choque) > 8 else ''
        raise RelatorioInvalido(
            f'Estes números já estão em uso: {amostra}{extra}.')
    if len(set(numeros)) != len(numeros):
        raise RelatorioInvalido('Há número de relatório repetido na lista.')

    processos = []
    for numero, num_proc in zip(numeros, processos_txt):
        processo = _buscar_processo_para_destino(num_proc, grupo)
        if processo.numero_relatorio and not processo.sem_relatorio:
            raise RelatorioInvalido(
                f'O processo {num_proc} já tem relatório '
                f'{processo.numero_relatorio}.')
        if any(p.id == processo.id for p in processos):
            raise RelatorioInvalido(
                f'O processo {num_proc} foi informado mais de uma vez.')
        processos.append(processo)

    agora = timezone.now()
    quantidade = len(numeros)
    for numero, processo in zip(numeros, processos):
        _remover_linha_cancelada_do_numero(grupo, numero)
        ReservaNumeroRelatorio.objects.create(
            grupo=grupo, numero=numero, data=data_reserva,
            criado_por=usuario, processo=processo, usado_em=agora)
        processo.numero_relatorio = str(numero)
        processo.data_analise = data_reserva
        processo.sem_relatorio = True
        if not (processo.observacao or '').strip():
            processo.observacao = 'Sem relatório — número reservado e vinculado.'
        processo.save(update_fields=[
            'numero_relatorio', 'data_analise', 'sem_relatorio', 'observacao'])
        registrar(processo)
    return {'quantidade': quantidade, 'numeros': numeros}


def _normalizar_pares(pares):
    """Converte [(processo, numero), ...] em listas paralelas validadas."""
    if not pares:
        raise RelatorioInvalido('Adicione ao menos um processo.')
    processos_txt = []
    numeros = []
    for item in pares:
        if item is None or len(item) != 2:
            raise RelatorioInvalido('Cada linha precisa de processo e número.')
        num_proc = str(item[0] or '').strip()
        if not num_proc:
            raise RelatorioInvalido('Informe o número do processo em cada linha.')
        try:
            numero = int(str(item[1]).strip())
        except (TypeError, ValueError):
            raise RelatorioInvalido(
                f'Informe o número de relatório do processo {num_proc}.')
        if numero < 1:
            raise RelatorioInvalido(
                f'O número de relatório do processo {num_proc} '
                f'deve ser maior que zero.')
        processos_txt.append(num_proc)
        numeros.append(numero)
    return numeros, processos_txt


def sugerir_numeros_disponiveis(grupo, quantidade, ocupados=None, excluir=None):
    """Próximos N números livres: usa cancelados (vermelho) e segue a sequência."""
    try:
        quantidade = int(str(quantidade).strip())
    except (TypeError, ValueError):
        raise RelatorioInvalido('Informe quantos números deseja gerar.')
    if quantidade < 1:
        raise RelatorioInvalido('A quantidade deve ser maior que zero.')
    if quantidade > LIMITE_DESTINO:
        raise RelatorioInvalido(
            f'Destine no máximo {LIMITE_DESTINO} números por vez.')
    if ocupados is None:
        ocupados = numeros_usados(grupo) | _numeros_reservados(grupo)
    else:
        ocupados = set(ocupados)
    if excluir:
        for item in excluir:
            numero = _inteiro(item)
            if numero:
                ocupados.add(numero)

    escolhidos = []
    # 1) Reaproveita números cancelados (vermelhos), em ordem.
    for bruto in (LinhaControleRelatorio.objects
                  .filter(filtro_sequencia(grupo),
                          situacao_linha=LinhaControleRelatorio.SITUACAO_CANCELADA)
                  .exclude(numero_relatorio='')
                  .values_list('numero_relatorio', flat=True)):
        numero = _inteiro(bruto)
        if numero and numero not in ocupados and numero not in escolhidos:
            escolhidos.append(numero)
        if len(escolhidos) >= quantidade:
            break
    escolhidos.sort()
    escolhidos = escolhidos[:quantidade]

    # 2) Completa com a sequência a partir do próximo do contador.
    if len(escolhidos) < quantidade:
        atual = max(int(estado_sequencia(grupo)['proximo'] or 1), 1)
        while len(escolhidos) < quantidade:
            if atual not in ocupados and atual not in escolhidos:
                escolhidos.append(atual)
            atual += 1
            if atual > 10_000_000:
                raise RelatorioInvalido(
                    'Não foi possível gerar tantos números disponíveis.')
    return escolhidos


def _remover_linha_cancelada_do_numero(grupo, numero):
    """Tira a linha vermelha ao reaproveitar o número na reserva vinculada."""
    (LinhaControleRelatorio.objects
     .filter(filtro_sequencia(grupo), numero_relatorio=str(numero),
             situacao_linha=LinhaControleRelatorio.SITUACAO_CANCELADA,
             processo__isnull=True)
     .delete())


def _parse_numeros_processo(bruto):
    if bruto is None:
        return []
    if isinstance(bruto, (list, tuple)):
        itens = [str(x).strip() for x in bruto]
    else:
        itens = str(bruto).replace(';', '\n').replace(',', '\n').splitlines()
    return [item for item in (x.strip() for x in itens) if item]


def _buscar_processo_para_destino(numero_processo, grupo):
    numero = (numero_processo or '').strip()
    processo = (Processo.objects
                .filter(numero_processo__iexact=numero)
                .order_by('-id')
                .first())
    if processo is None:
        raise RelatorioInvalido(
            f'Processo {numero} não encontrado. Cadastre a entrada no '
            f'Protocolo antes de vincular o número.')
    if not especie_gera_relatorio(processo):
        raise RelatorioInvalido(
            f'A espécie de {numero} não gera número de relatório.')
    sequencia = sequencia_do_processo(processo) or GRUPO_PADRAO
    if sequencia != grupo:
        nome = info_sequencia(sequencia)['nome']
        raise RelatorioInvalido(
            f'O processo {numero} pertence à sequência {nome}, '
            f'não a {info_sequencia(grupo)["nome"]}.')
    return processo


@transaction.atomic
def cancelar_destino(usuario, reserva_id):
    perm.assert_permissao(
        perm.pode_destinar_numeros_relatorio(usuario),
        'Somente analista de Liquidações e o administrador cancelam destinos.')
    reserva = ReservaNumeroRelatorio.objects.filter(id=reserva_id).first()
    if reserva is None:
        raise RelatorioInvalido('Destino não encontrado.')
    if reserva.processo_id:
        raise RelatorioInvalido(
            'Este número já está vinculado a um processo. '
            'Use Apagar no Controle de relatório se precisar remover a linha.')
    reserva.delete()
    return reserva.numero


def _chave_cabecalho(texto):
    bruto = unicodedata.normalize('NFKD', str(texto or ''))
    sem_acento = ''.join(c for c in bruto if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9]+', ' ', sem_acento.casefold()).strip()


_ALIAS_COLUNAS = {
    'numero_relatorio': (
        'numero', 'n relatorio', 'no relatorio', 'numero relatorio',
        'nº relatorio', 'num relatorio', 'relatorio',
    ),
    'data_relatorio': ('data', 'data relatorio', 'data do relatorio'),
    'analista': ('relator', 'analista', 'tecnico'),
    'processo_pagamento': (
        'processo de prestacao', 'processo prestacao',
        'processo pagamento', 'proc pagamento',
    ),
    'processo_origem': (
        'processo de concessao', 'processo concessao',
        'processo origem', 'proc origem',
        'n do processo', 'n processo', 'numero processo', 'nº processo',
        'processo',
    ),
    'secretaria': ('secretaria', 'secretaria de origem'),
    'objeto': (
        'objeto', 'assunto', 'evento',
        'necessidade concessao prestacao', 'necessidade',
    ),
    'periodo': (
        'periodo', 'nome do responsavel', 'quant', 'quantidade',
    ),
    'modalidade': ('modalidade',),
    'valor': ('valor', 'valor total'),
    'destino': ('destino', 'enviado para'),
    'contratada': (
        'contratada', 'favorecido', 'contratada favorecido', 'servidor',
        'interessado', 'entidade', 'beneficiario', 'bloco',
        'nome do atleta',
    ),
    'observacao_planilha': ('obs', 'observacao'),
}

# Mapa por grupo: evita colisões (ex.: Assunto vs Evento/Necessidade).
_ALIAS_POR_GRUPO = {
    'ADIANTAMENTO': {
        'numero_relatorio': ('numero',),
        'contratada': ('servidor',),
        'valor': ('valor',),
        'processo_origem': (
            'n do processo', 'n processo', 'numero processo', 'nº processo',
        ),
        'objeto': ('assunto',),
        'data_relatorio': ('data',),
        'destino': ('enviado para', 'destino'),
        'secretaria': ('secretaria de origem', 'secretaria'),
    },
    'COTA_PATROCINIO': {
        'numero_relatorio': ('numero',),
        'contratada': ('interessado',),
        'objeto': ('evento',),
        'valor': ('valor',),
        'processo_origem': (
            'n do processo', 'n processo', 'numero processo', 'nº processo',
        ),
        'periodo': ('assunto',),
        'data_relatorio': ('data',),
        'destino': ('enviado para', 'destino'),
        'observacao_planilha': ('obs', 'observacao'),
    },
    'SUBVENCAO': {
        'numero_relatorio': ('numero',),
        'contratada': ('entidade',),
        'valor': ('valor',),
        'processo_origem': (
            'n do processo', 'n processo', 'numero processo', 'nº processo',
        ),
        'periodo': ('assunto',),
        'objeto': ('necessidade',),
        'data_relatorio': ('data',),
        'destino': ('enviado para', 'destino'),
        'observacao_planilha': ('obs', 'observacao'),
    },
    'ALUGUEL_SOCIAL': {
        'numero_relatorio': ('numero',),
        'contratada': ('beneficiario',),
        'valor': ('valor',),
        'processo_origem': (
            'n do processo', 'n processo', 'numero processo', 'nº processo',
        ),
        'objeto': ('assunto',),
        'data_relatorio': ('data',),
        'destino': ('enviado para', 'destino'),
        'observacao_planilha': ('obs', 'observacao'),
    },
    'BOLSA_ATLETA': {
        'numero_relatorio': ('numero',),
        'contratada': ('nome do atleta',),
        'periodo': ('nome do responsavel',),
        'valor': ('valor',),
        'processo_origem': (
            'processo de concessao', 'processo concessao',
        ),
        'processo_pagamento': (
            'processo de prestacao', 'processo prestacao',
        ),
        'objeto': ('assunto',),
        'modalidade': ('modalidade',),
        'data_relatorio': ('data',),
        'destino': ('enviado para', 'destino'),
        'observacao_planilha': ('obs', 'observacao'),
    },
    'AUXILIO_COMPETICAO': {
        'numero_relatorio': ('numero',),
        'contratada': ('nome do atleta',),
        'periodo': ('nome do responsavel',),
        'valor': ('valor',),
        'processo_origem': (
            'processo de concessao', 'processo concessao',
        ),
        'processo_pagamento': (
            'processo de prestacao', 'processo prestacao',
        ),
        'objeto': ('assunto',),
        'modalidade': ('modalidade',),
        'data_relatorio': ('data',),
        'destino': ('enviado para', 'destino'),
        'observacao_planilha': ('obs', 'observacao'),
    },
    'DIARIA': {
        'numero_relatorio': ('numero',),
        'secretaria': ('secretaria',),
        'contratada': ('servidor',),
        'periodo': ('quant', 'quantidade'),
        'valor': ('valor total', 'valor'),
        'processo_origem': (
            'n do processo', 'n processo', 'numero processo', 'nº processo',
        ),
        'objeto': ('assunto',),
        'data_relatorio': ('data',),
        'destino': ('enviado para', 'destino'),
    },
    'BLOCOS_CARNAVALESCOS': {
        'numero_relatorio': ('numero',),
        'contratada': ('bloco',),
        'valor': ('valor',),
        'processo_origem': (
            'n do processo', 'n processo', 'numero processo', 'nº processo',
        ),
        'objeto': ('assunto',),
        'data_relatorio': ('data',),
        'destino': ('enviado para', 'destino'),
        'observacao_planilha': ('obs', 'observacao'),
    },
}


def _campo_por_chave(chave, aliases_dict, campos_ja):
    """Escolhe o campo que melhor casa com o cabeçalho (exato > parcial)."""
    candidatos = []
    for campo, aliases in aliases_dict.items():
        if campo in campos_ja:
            continue
        for alias in aliases:
            if not alias:
                continue
            if chave == alias:
                candidatos.append((0, -len(alias), campo))
            elif alias in chave:
                candidatos.append((1, -len(alias), campo))
    if not candidatos:
        return None
    candidatos.sort()
    return candidatos[0][2]


def _mapear_cabecalhos(linha, grupo=None):
    """Mapeia índices de coluna → campo. Usa layout do grupo quando conhecido."""
    mapa = {}
    usados = set()
    aliases = _ALIAS_POR_GRUPO.get(grupo) if grupo else None

    for indice, celula in enumerate(linha):
        chave = _chave_cabecalho(celula)
        if not chave:
            continue
        campo = None
        if aliases:
            campo = _campo_por_chave(chave, aliases, mapa)
        if campo is None:
            campo = _campo_por_chave(chave, _ALIAS_COLUNAS, mapa)
        if campo is None:
            continue
        mapa[campo] = indice
        usados.add(indice)

    # Aluguel Social: 1ª…5ª parcela → periodo combinado.
    parcelas = []
    for indice, celula in enumerate(linha):
        if indice in usados:
            continue
        chave = _chave_cabecalho(celula)
        if chave and 'parcela' in chave:
            parcelas.append(indice)
            usados.add(indice)
    if parcelas:
        mapa['parcelas'] = parcelas
    return mapa


def _sequencia_por_nome_aba(nome_aba):
    """Mapeia o título da aba Excel para o código da sequência de relatório."""
    chave = _chave_cabecalho(nome_aba)
    if not chave:
        return None
    if 'medicao anual' in chave:
        # Aba complementar (vários blocos por secretaria); use ADIANTAMENTOS.
        return None
    if 'aux' in chave and 'competicao' in chave:
        return 'AUXILIO_COMPETICAO'
    if 'adiantamento' in chave:
        return 'ADIANTAMENTO'
    if 'cota' in chave and 'patrocinio' in chave:
        return 'COTA_PATROCINIO'
    if 'subvencao' in chave:
        return 'SUBVENCAO'
    if 'aluguel' in chave and 'social' in chave:
        return 'ALUGUEL_SOCIAL'
    if 'bolsa' in chave and 'atleta' in chave:
        return 'BOLSA_ATLETA'
    if 'diaria' in chave:
        return 'DIARIA'
    if 'bloco' in chave:
        return 'BLOCOS_CARNAVALESCOS'
    if 'controle' in chave or 'liquidacao' in chave or 'liquidacoes' in chave:
        return GRUPO_PADRAO
    return None


def _escolher_aba_planilha(workbook, grupo=None):
    if grupo and grupo not in (GRUPO_IMPORTACAO_COMPLETA,):
        for nome in workbook.sheetnames:
            if _sequencia_por_nome_aba(nome) == grupo:
                return workbook[nome]
        raise RelatorioInvalido(
            f'Não achei a aba do grupo {info_sequencia(grupo)["nome"]} '
            f'neste arquivo. Se for o Excel unificado 2026, escolha '
            f'“Todas as abas do arquivo”.'
        )
    for nome in workbook.sheetnames:
        if 'controle' in _chave_cabecalho(nome):
            return workbook[nome]
    return workbook[workbook.sheetnames[0]]


def _localizar_cabecalho(planilha, grupo=None, max_row=25):
    for indice, row in enumerate(
            planilha.iter_rows(min_row=1, max_row=max_row, values_only=True), 1):
        mapa = _mapear_cabecalhos(row, grupo=grupo)
        if 'numero_relatorio' not in mapa:
            continue
        if (
                'data_relatorio' in mapa
                or 'processo_pagamento' in mapa
                or 'processo_origem' in mapa
                or 'objeto' in mapa
                or 'contratada' in mapa
                or 'periodo' in mapa):
            return indice, mapa
    raise RelatorioInvalido(
        'Não encontrei o cabeçalho da planilha. '
        'É preciso ter colunas de Nº relatório e Data, Processo ou Assunto.')


def _texto_celula(valor, limite=255):
    if valor is None:
        return ''
    if isinstance(valor, datetime):
        return valor.date().isoformat()
    if isinstance(valor, date):
        return valor.isoformat()
    if isinstance(valor, float) and valor.is_integer():
        texto = str(int(valor))
    else:
        texto = str(valor).strip()
    if len(texto) > limite:
        return texto[: limite - 1] + '…'
    return texto


def _data_celula(valor):
    if valor is None or valor == '':
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    try:
        return converter_data(valor)
    except ValidationError:
        return None


def _numero_relatorio_celula(valor):
    if valor is None or valor == '':
        return ''
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    if isinstance(valor, int):
        return str(valor)
    texto = str(valor).strip()
    if not texto:
        return ''
    # "56 A", "1488 A" etc. permanecem como texto.
    return texto


def _celula_amarela(celula):
    """Amarelo puro da planilha CGM = reservado / saiu sem análise.

    Não confundir com laranja (FFC000), usado em faixas vazias da planilha.
    """
    if celula is None:
        return False
    preenchimento = celula.fill
    if (
        preenchimento is None
        or not preenchimento.fill_type
        or preenchimento.fill_type == 'none'
    ):
        return False
    cor = getattr(preenchimento, 'fgColor', None)
    if cor is None or getattr(cor, 'type', None) != 'rgb':
        return False
    try:
        rgb = cor.rgb
    except (TypeError, ValueError, AttributeError):
        return False
    if not rgb:
        return False
    codigo = str(rgb).upper()
    # Amarelo clássico do Excel: FFFFFF00 (e variantes claras).
    return codigo.endswith('FFFF00') or codigo in {
        'FFFFFF00', 'FFFFEB9C', 'FFFFF2CC', 'FFFFFF99',
    }


def _linha_amarela(celulas):
    return any(_celula_amarela(celula) for celula in celulas[:12])


def _importar_linhas_aba(planilha, linha_cabecalho, colunas, grupo, existentes):
    """Lê linhas de uma aba já com cabeçalho mapeado; retorna contadores."""
    idx_num = colunas['numero_relatorio']
    criadas = atualizadas = ignoradas = 0
    maior_inteiro = 0
    hoje = timezone.localdate()
    criar_lote = []
    atualizar_lote = []
    atualizar_ids = set()
    campos_update = [
        'numero_processo', 'volume', 'data_relatorio', 'secretaria',
        'contratada', 'objeto', 'valor', 'periodo', 'destino', 'analista',
        'observacao', 'grupo', 'sequencia', 'situacao_linha', 'sem_relatorio',
        'status_analise',
    ]

    for row in planilha.iter_rows(min_row=linha_cabecalho + 1):
        if row is None:
            continue
        valores = [celula.value for celula in row]
        numero_txt = _numero_relatorio_celula(
            valores[idx_num] if idx_num < len(valores) else None)
        if not numero_txt:
            continue

        # Amarelo = “saiu sem análise” só na planilha de Liquidação.
        # Nos demais grupos a cor da célula não altera o status.
        amarela = (
            grupo == GRUPO_PADRAO and _linha_amarela(row)
        )

        def cel(campo, _valores=valores):
            indice = colunas.get(campo)
            if indice is None or indice >= len(_valores):
                return None
            return _valores[indice]

        pagamento = _texto_celula(cel('processo_pagamento'))
        origem = _texto_celula(cel('processo_origem'))
        # Bolsa/Auxílio: prestação → numero_processo; concessão → volume.
        if grupo in ('BOLSA_ATLETA', 'AUXILIO_COMPETICAO'):
            if pagamento and origem:
                numero_processo, volume_proc = pagamento, origem
            elif pagamento:
                numero_processo, volume_proc = pagamento, ''
            else:
                # Só concessão: coluna prestação vazia; nº fica em volume.
                numero_processo, volume_proc = '', origem
        else:
            # Pagamento = nº na planilha; origem fica em volume.
            numero_processo = pagamento or origem
            volume_proc = (
                origem
                if pagamento and origem and pagamento != origem
                else ''
            )
        data_bruta = cel('data_relatorio')
        data = _data_celula(data_bruta)
        nota_data = ''
        if data is None and data_bruta not in (None, ''):
            # Ex.: célula "Cancelado" no lugar da data.
            nota_data = _texto_celula(data_bruta, limite=120)
        analista = _texto_celula(cel('analista'))
        secretaria = _texto_celula(cel('secretaria'))
        contratada = _texto_celula(cel('contratada'))
        objeto = _texto_celula(cel('objeto'), limite=5000)
        modalidade = _texto_celula(cel('modalidade'))
        if modalidade:
            objeto = (
                f'{objeto} — {modalidade}' if objeto else modalidade
            )[:5000]
        obs_planilha = _texto_celula(cel('observacao_planilha'), limite=500)
        periodo = _texto_celula(cel('periodo'))
        idxs_parcelas = colunas.get('parcelas') or []
        if not periodo and idxs_parcelas:
            partes = []
            for n, idx in enumerate(idxs_parcelas, 1):
                if idx >= len(valores):
                    continue
                trecho = _texto_celula(valores[idx])
                if trecho:
                    partes.append(f'{n}ª: {trecho}')
            periodo = ' · '.join(partes)[:255]
        destino = _texto_celula(cel('destino'))
        valor_bruto = cel('valor')
        if isinstance(valor_bruto, (int, float)):
            valor = (
                f"R$ {float(valor_bruto):,.2f}"
                .replace(',', 'X')
                .replace('.', ',')
                .replace('X', '.')
            )
        elif valor_bruto in (None, ''):
            valor = ''
        else:
            valor = formatar_valor(valor_bruto)

        # Pré-numerados vazios = ignorar.
        # Amarelo só conta como "saiu sem análise" se tiver algum dado
        # (data, relator, processo…). Só tinta amarela em linha vazia não entra.
        tem_conteudo = any((
            numero_processo, volume_proc, data, nota_data, analista,
            secretaria, contratada, objeto, periodo, destino, valor,
        ))
        if not tem_conteudo:
            continue
        if data is None:
            data = hoje

        obs = ['Importado da planilha Excel']
        if amarela:
            obs.append('Reservado / saiu sem análise (amarelo na planilha)')
        if nota_data:
            obs.append(nota_data)
        if obs_planilha:
            obs.append(obs_planilha)
        if (
            origem and pagamento and origem != pagamento
            and grupo not in ('BOLSA_ATLETA', 'AUXILIO_COMPETICAO')
        ):
            obs.append(f'Processo origem: {origem}')

        dados = {
            'numero_processo': numero_processo,
            'numero_relatorio': numero_txt,
            'data_relatorio': data,
            'secretaria': secretaria,
            'contratada': contratada,
            'objeto': objeto,
            'valor': valor[:255],
            'periodo': periodo,
            'destino': destino,
            'analista': analista,
            'observacao': ' · '.join(obs),
            # Sempre LIQUIDACOES: o analista filtra por genero/grupo.
            # A aba (Adiantamento, Bolsa…) fica em `sequencia`.
            'grupo': GRUPO_PADRAO,
            'sequencia': grupo,
            'situacao_linha': LinhaControleRelatorio.SITUACAO_HISTORICA,
            'sem_relatorio': amarela,
            'volume': volume_proc,
            'status_analise': '',
        }

        numero_int = _inteiro(numero_txt)
        if numero_int:
            maior_inteiro = max(maior_inteiro, numero_int)

        atual = existentes.get(numero_txt)
        if atual is not None:
            # Excel é a fonte da verdade: sobrescreve inclusive ATIVA ligada
            # a processo (corrige valor/secretaria/objeto digitados errados).
            # Mantém o vínculo e a situação ATIVA.
            manter_ativa = (
                atual.pk
                and atual.situacao_linha == LinhaControleRelatorio.SITUACAO_ATIVA
                and atual.processo_id
            )
            for campo, valor_campo in dados.items():
                if manter_ativa and campo == 'situacao_linha':
                    continue
                if manter_ativa and campo == 'sem_relatorio':
                    continue
                setattr(atual, campo, valor_campo)
            if manter_ativa:
                _sincronizar_processo_pela_importacao(atual.processo, dados)
            if atual.pk:
                if atual.pk not in atualizar_ids:
                    atualizar_lote.append(atual)
                    atualizar_ids.add(atual.pk)
                    atualizadas += 1
            # Duplicata no mesmo arquivo: só atualiza o objeto pendente.
            continue

        linha = LinhaControleRelatorio(processo=None, **dados)
        criar_lote.append(linha)
        existentes[numero_txt] = linha
        criadas += 1

        if len(criar_lote) >= 400:
            LinhaControleRelatorio.objects.bulk_create(criar_lote)
            criar_lote.clear()
        if len(atualizar_lote) >= 400:
            LinhaControleRelatorio.objects.bulk_update(
                atualizar_lote, campos_update)
            atualizar_lote.clear()

    if criar_lote:
        LinhaControleRelatorio.objects.bulk_create(criar_lote)
    if atualizar_lote:
        LinhaControleRelatorio.objects.bulk_update(
            atualizar_lote, campos_update)

    return criadas, atualizadas, ignoradas, maior_inteiro


def _atualizar_proximo_numero_grupo(grupo, maior_inteiro):
    """Recalcula o próximo nº pelo maior inteiro ainda usado no grupo."""
    usados = set(numeros_usados(grupo)) | set(_numeros_reservados(grupo))
    if maior_inteiro:
        usados.add(int(maior_inteiro))
    if usados:
        proximo = max(usados) + 1
    else:
        proximo = _proximo_padrao(grupo)
    seq, _ = SequenciaRelatorio.objects.select_for_update().get_or_create(
        grupo=grupo,
        defaults={'proximo_numero': proximo})
    if int(seq.proximo_numero or 0) != proximo:
        seq.proximo_numero = proximo
        seq.save(update_fields=['proximo_numero'])


def _limpar_historico_substituivel(grupo):
    """Remove histórico antigo do grupo antes de reimportar a planilha.

    Mantém linhas ATIVAS ainda ligadas a processo (análise viva) — esses
    campos serão sobrescritos pelo Excel na importação, sem desvincular.
    Qualquer linha sem processo (histórico, órfã, reservada…) é substituída.
    """
    return (
        LinhaControleRelatorio.objects
        .filter(filtro_sequencia(grupo), processo__isnull=True)
        .delete()
    )


_CAMPOS_OBRIGATORIOS_IMPORT = {
    'ADIANTAMENTO': ('numero_relatorio', 'contratada'),
    'COTA_PATROCINIO': ('numero_relatorio', 'contratada'),
    'SUBVENCAO': ('numero_relatorio', 'contratada'),
    'ALUGUEL_SOCIAL': ('numero_relatorio', 'contratada'),
    'BOLSA_ATLETA': ('numero_relatorio', 'contratada'),
    'AUXILIO_COMPETICAO': ('numero_relatorio', 'contratada'),
    'DIARIA': ('numero_relatorio', 'secretaria'),
    'BLOCOS_CARNAVALESCOS': ('numero_relatorio', 'contratada'),
}


def _validar_cabecalho_grupo(grupo, colunas):
    """Impede importar planilha de Liquidação no grupo errado (e vice-versa)."""
    obrigatorios = _CAMPOS_OBRIGATORIOS_IMPORT.get(grupo)
    if not obrigatorios:
        return
    faltando = [c for c in obrigatorios if c not in colunas]
    if faltando:
        raise RelatorioInvalido(
            f'A aba não parece ser de {info_sequencia(grupo)["nome"]}. '
            f'Confira se escolheu o arquivo/aba certos '
            f'(ex.: Adiantamento tem coluna Servidor; '
            f'Liquidação tem Relator/Objeto).'
        )


def _existentes_por_grupo(grupo):
    return {
        (linha.numero_relatorio or '').strip(): linha
        for linha in (
            LinhaControleRelatorio.objects
            .select_for_update()
            .filter(filtro_sequencia(grupo))
            .exclude(numero_relatorio='')
        )
    }


def _importar_aba_excel(planilha, grupo):
    linha_cabecalho, colunas = _localizar_cabecalho(planilha, grupo=grupo)
    _validar_cabecalho_grupo(grupo, colunas)
    # Substitui o histórico antigo desse grupo (não mistura com outra planilha).
    apagadas, _ = _limpar_historico_substituivel(grupo)
    existentes = _existentes_por_grupo(grupo)
    criadas, atualizadas, ignoradas, maior_inteiro = _importar_linhas_aba(
        planilha, linha_cabecalho, colunas, grupo, existentes)
    _atualizar_proximo_numero_grupo(grupo, maior_inteiro)
    return {
        'grupo': grupo,
        'nome': info_sequencia(grupo)['nome'],
        'criadas': criadas,
        'atualizadas': atualizadas,
        'ignoradas': ignoradas,
        'apagadas': apagadas or 0,
        'proximo': estado_sequencia(grupo)['proximo'],
    }


@transaction.atomic
def importar_planilha_excel(usuario, arquivo, grupo=GRUPO_PADRAO):
    """Importa números antigos de um .xlsx para o Controle de relatório.

    Antes de importar cada grupo, apaga o histórico antigo desse grupo
    (HISTORICA/CANCELADA/RESERVADA sem processo) e recalcula o próximo nº.
    Análises ATIVAS ligadas a processo **permanecem vinculadas**, mas os
    campos da planilha (valor, objeto, secretaria…) são sobrescritos —
    a planilha Excel é a fonte da verdade.

    Com ``grupo=GRUPO_IMPORTACAO_COMPLETA`` importa todas as abas
    reconhecidas (arquivo unificado Controle Relatórios 2026).
    """
    perm.assert_permissao(
        perm.pode_definir_ultimo_relatorio(usuario),
        'Somente o administrador importa planilha de relatório.')
    if grupo != GRUPO_IMPORTACAO_COMPLETA and not sequencia_valida(grupo):
        raise RelatorioInvalido('Sequência de relatório inválida.')
    if arquivo is None:
        raise RelatorioInvalido('Selecione o arquivo Excel (.xlsx).')
    nome = (getattr(arquivo, 'name', '') or '').lower()
    if not nome.endswith('.xlsx'):
        raise RelatorioInvalido('Envie um arquivo .xlsx (Excel).')

    try:
        from openpyxl import load_workbook
    except ImportError as exc:
        raise RelatorioInvalido(
            'Biblioteca openpyxl indisponível no servidor.') from exc

    # data_only=False: precisa da cor da célula para achar linhas amarelas.
    try:
        workbook = load_workbook(arquivo, data_only=False)
    except Exception as exc:
        raise RelatorioInvalido(
            'Não foi possível ler o Excel. Verifique se o arquivo não está '
            'corrompido ou aberto em outro programa.') from exc

    if grupo == GRUPO_IMPORTACAO_COMPLETA:
        resultados = []
        puladas = []
        total_c = total_a = total_i = 0
        for nome_aba in workbook.sheetnames:
            codigo = _sequencia_por_nome_aba(nome_aba)
            if not codigo:
                puladas.append(nome_aba)
                continue
            try:
                parcial = _importar_aba_excel(workbook[nome_aba], codigo)
            except RelatorioInvalido:
                puladas.append(nome_aba)
                continue
            if parcial['criadas'] + parcial['atualizadas'] + parcial['ignoradas'] == 0:
                continue
            resultados.append(parcial)
            total_c += parcial['criadas']
            total_a += parcial['atualizadas']
            total_i += parcial['ignoradas']
        if not resultados:
            raise RelatorioInvalido(
                'Nenhuma aba reconhecida com linhas para importar. '
                'Verifique se o arquivo é o Controle Relatórios (.xlsx) '
                'com abas como ADIANTAMENTOS, DIÁRIAS, BOLSA ATLETA…')
        return {
            'multi': True,
            'grupo': GRUPO_IMPORTACAO_COMPLETA,
            'nome': 'Todas as abas',
            'abas': resultados,
            'puladas': puladas,
            'criadas': total_c,
            'atualizadas': total_a,
            'ignoradas': total_i,
            'proximo': None,
        }

    planilha = _escolher_aba_planilha(workbook, grupo=grupo)
    resultado = _importar_aba_excel(planilha, grupo)
    if (
        resultado['criadas'] + resultado['atualizadas'] == 0
        and resultado['ignoradas'] == 0
    ):
        raise RelatorioInvalido(
            'Nenhuma linha com número de relatório foi encontrada na planilha.')
    return resultado
