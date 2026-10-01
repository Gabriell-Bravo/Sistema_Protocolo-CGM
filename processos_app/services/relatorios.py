# processos_app/services/relatorios.py
"""Controle de relatório: sequência numérica e planilha das análises.

Cada espécie de Liquidações pertence a uma sequência de numeração
(Liquidação, Adiantamento, Bolsa Atleta…). O administrador informa o
último número de cada sequência. O número é gerado ao salvar a análise.
"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, IntegerField, Q
from django.db.models.functions import Cast
from django.utils import timezone

from ..models import (
    LinhaControleRelatorio, Processo, ReservaNumeroRelatorio, SequenciaRelatorio,
)
from . import permissions as perm
from .eventos import registrar_diff
from .processos import converter_data


# Código legado da sequência geral (continua no banco como LIQUIDACOES).
GRUPO_PADRAO = perm.GRUPO_LIQUIDACOES
LIMITE_DESTINO = 80

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
        'especies': (),
        'resumo': (
            'Inclui (Auxílio Competição — ajuda de custo). '
            'Espécie ainda não cadastrada no sistema.'
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

# Por enquanto só Liquidação gera/consome número. As outras abas e o mapa
# de espécies ficam prontos; inclua o código em SEQUENCIAS_ATIVAS quando
# for liberar a numeração própria de cada grupo.
SEQUENCIAS_ATIVAS = frozenset({GRUPO_PADRAO})


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
    """Código da sequência de numeração conforme a espécie.

    Espécies de grupos ainda não liberados entram na sequência Liquidação.
    """
    if not especie_gera_relatorio(processo):
        return None
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
    """Números ainda presos a uma análise nesta sequência."""
    ignorar = set(ignorar or ())
    usados = set()
    for bruto in (LinhaControleRelatorio.objects
                  .filter(processo__isnull=False)
                  .filter(filtro_sequencia(grupo))
                  .exclude(numero_relatorio='')
                  .values_list('numero_relatorio', flat=True)):
        numero = _inteiro(bruto)
        if numero:
            usados.add(numero)
    return usados - ignorar


def _numeros_devolvidos(grupo, usados):
    """Números de análises desistidas, ainda não reaproveitados."""
    livres = []
    for bruto in (LinhaControleRelatorio.objects
                  .filter(processo__isnull=True)
                  .filter(filtro_sequencia(grupo))
                  .exclude(numero_relatorio='')
                  .values_list('numero_relatorio', flat=True)):
        numero = _inteiro(bruto)
        if numero and numero not in usados:
            livres.append(numero)
    return livres


def _buracos_na_sequencia(usados, proximo):
    """Números pulados abaixo do contador (ex.: alguém informou 1904 e
    o 1903 nunca foi emitido). Só olha a faixa já iniciada nesta sequência.
    """
    if proximo < 2:
        return []
    abaixo = [n for n in usados if n < proximo]
    if not abaixo:
        return []
    inicio = min(abaixo)
    return [n for n in range(inicio, proximo) if n not in usados]


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
        processo__isnull=True
    ).filter(filtro_sequencia(grupo)).delete()
    return estado_sequencia(grupo)


def proximo_numero(grupo):
    """Trava a sequência para dois salvamentos não saírem iguais.

    Ordem: número devolvido (desistência) → buraco na sequência → próximo
    do contador.
    """
    SequenciaRelatorio.objects.get_or_create(
        grupo=grupo, defaults={'proximo_numero': _proximo_padrao(grupo)})
    seq = SequenciaRelatorio.objects.select_for_update().get(grupo=grupo)
    usados = numeros_usados(grupo) | _numeros_reservados(grupo)
    livres = _numeros_devolvidos(grupo, usados)
    if not livres:
        livres = _buracos_na_sequencia(usados, int(seq.proximo_numero or 1))
    if livres:
        numero = min(livres)
        LinhaControleRelatorio.objects.filter(
            processo__isnull=True, numero_relatorio=str(numero)
        ).filter(filtro_sequencia(grupo)).delete()
        return str(numero)

    numero = int(seq.proximo_numero or 1)
    if numero < 1:
        numero = 1
    while numero in usados:
        numero += 1
    seq.proximo_numero = numero + 1
    seq.save(update_fields=['proximo_numero'])
    return str(numero)


def atribuir_se_preciso(processo):
    """Gera o número só se a espécie gera relatório e o processo ainda não tem.

    Não grava o processo: o chamador inclui `numero_relatorio` no save.
    """
    if not especie_gera_relatorio(processo):
        return False
    if processo.numero_relatorio:
        registrar(processo)
        return False
    sequencia = sequencia_do_processo(processo)
    if not sequencia:
        return False
    processo.numero_relatorio = proximo_numero(sequencia)
    registrar(processo)
    return True


def _inteiro_atual(processo):
    try:
        return int(str(processo.numero_relatorio).strip())
    except (TypeError, ValueError):
        return None


@transaction.atomic
def alterar_numero(usuario, processo_id, novo, data=None):
    """Analista do grupo ou administrador grava o número e a data do relatório."""
    processo = (Processo.objects.select_for_update()
                .filter(id=processo_id).first())
    if processo is None:
        raise RelatorioInvalido('Processo não encontrado.')
    perm.assert_permissao(
        perm.pode_editar_numero_relatorio(usuario, processo),
        'Somente o analista do grupo e o administrador alteram o número.')
    if not especie_gera_relatorio(processo):
        raise RelatorioInvalido('Esta espécie não gera número de relatório.')
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

    atual = _inteiro_atual(processo)
    campos = []
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
    return processo


def registrar(processo):
    """Cria ou atualiza a linha da planilha a partir do processo."""
    if not processo.numero_relatorio:
        return None
    dados = _dados_da_linha(processo)
    linha, _ = LinhaControleRelatorio.objects.update_or_create(
        processo=processo, defaults=dados)
    return linha


def remover_do_processo(processo):
    """Desvincula a linha. O número volta a ser o próximo a ser gerado."""
    LinhaControleRelatorio.objects.filter(processo=processo).update(processo=None)
    _liberar_reservas_do_processo(processo)


def listar(usuario, sequencia=None):
    consulta = LinhaControleRelatorio.objects.filter(processo__isnull=False)
    if perm.eh_administrador(usuario) or perm.is_gestao(usuario):
        pass
    elif perm.is_analista(usuario):
        grupo = perm.grupo_do_analista(usuario)
        if grupo:
            consulta = consulta.filter(grupo=grupo)
        else:
            return consulta.none()
    else:
        return consulta.none()
    if sequencia:
        consulta = consulta.filter(filtro_sequencia(sequencia))
    return consulta.annotate(
        numero_ordem=Cast('numero_relatorio', IntegerField())
    ).order_by('numero_ordem', 'id')


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
    return {
        'numero_processo': processo.numero_processo or '',
        'volume': processo.volume or '',
        'numero_relatorio': processo.numero_relatorio or '',
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
        'sequencia': sequencia_do_processo(processo) or GRUPO_PADRAO,
    }


@transaction.atomic
def destinar_numeros(usuario, inicio, fim, data, grupo=GRUPO_PADRAO):
    """Guarda uma faixa de números com a mesma data para uso posterior."""
    perm.assert_permissao(
        perm.pode_destinar_numeros_relatorio(usuario),
        'Somente analista de Liquidações e o administrador destinam números.')
    if not sequencia_valida(grupo):
        raise RelatorioInvalido('Sequência de relatório inválida.')
    try:
        inicio = int(str(inicio).strip())
        fim = int(str(fim).strip())
    except (TypeError, ValueError):
        raise RelatorioInvalido('Informe o número inicial e o final.')
    if inicio < 1 or fim < 1:
        raise RelatorioInvalido('Os números devem ser maiores que zero.')
    if fim < inicio:
        inicio, fim = fim, inicio
    quantidade = fim - inicio + 1
    if quantidade > LIMITE_DESTINO:
        raise RelatorioInvalido(
            f'Destine no máximo {LIMITE_DESTINO} números por vez.')
    try:
        data_reserva = converter_data(data)
    except ValidationError as exc:
        raise RelatorioInvalido('; '.join(exc.messages))
    if data_reserva is None:
        raise RelatorioInvalido('Informe a data desses números.')

    faixa = set(range(inicio, fim + 1))
    ocupados = numeros_usados(grupo) | _numeros_reservados(grupo)
    choque = sorted(faixa & ocupados)
    if choque:
        amostra = ', '.join(str(n) for n in choque[:8])
        extra = '…' if len(choque) > 8 else ''
        raise RelatorioInvalido(
            f'Estes números já estão em uso ou destinados: {amostra}{extra}.')

    ReservaNumeroRelatorio.objects.bulk_create([
        ReservaNumeroRelatorio(
            grupo=grupo, numero=numero, data=data_reserva, criado_por=usuario)
        for numero in range(inicio, fim + 1)
    ])
    return quantidade


@transaction.atomic
def cancelar_destino(usuario, reserva_id):
    perm.assert_permissao(
        perm.pode_destinar_numeros_relatorio(usuario),
        'Somente analista de Liquidações e o administrador cancelam destinos.')
    reserva = ReservaNumeroRelatorio.objects.filter(id=reserva_id).first()
    if reserva is None:
        raise RelatorioInvalido('Destino não encontrado.')
    if reserva.processo_id:
        raise RelatorioInvalido('Este número já foi usado numa análise.')
    reserva.delete()
    return reserva.numero
