# processos_app/services/relatorios.py
"""Controle de relatório: sequência numérica e planilha das análises.

Cada espécie de Liquidações pertence a uma sequência de numeração
(Liquidação, Adiantamento, Bolsa Atleta…). O administrador informa o
último número de cada sequência. O número é gerado ao salvar a análise.
"""

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

# Sequências que já geram número próprio pela espécie.
# Auxílio Competição fica de fora até a espécie ser cadastrada.
SEQUENCIAS_ATIVAS = frozenset({
    GRUPO_PADRAO,
    'ADIANTAMENTO',
    'COTA_PATROCINIO',
    'SUBVENCAO',
    'ALUGUEL_SOCIAL',
    'BOLSA_ATLETA',
    'DIARIA',
    'BLOCOS_CARNAVALESCOS',
})


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
    """Números ainda presos nesta sequência (ativos ou guardados)."""
    ignorar = set(ignorar or ())
    usados = set()
    consulta = (LinhaControleRelatorio.objects
                .filter(filtro_sequencia(grupo))
                .exclude(numero_relatorio='')
                .exclude(situacao_linha=LinhaControleRelatorio.SITUACAO_CANCELADA)
                .filter(
                    Q(situacao_linha=LinhaControleRelatorio.SITUACAO_RESERVADA)
                    | Q(processo__isnull=False)
                ))
    for bruto in consulta.values_list('numero_relatorio', flat=True):
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
                  .filter(situacao_linha=LinhaControleRelatorio.SITUACAO_ATIVA)
                  .exclude(numero_relatorio='')
                  .values_list('numero_relatorio', flat=True)):
        numero = _inteiro(bruto)
        if numero and numero not in usados:
            livres.append(numero)
    return livres


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

    Usa somente o contador definido pelo administrador (e avançado
    automaticamente). Números antigos soltos na planilha — de desistência
    ou de digitação manual — não voltam a ser emitidos.
    """
    SequenciaRelatorio.objects.get_or_create(
        grupo=grupo, defaults={'proximo_numero': _proximo_padrao(grupo)})
    seq = SequenciaRelatorio.objects.select_for_update().get(grupo=grupo)
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


def atribuir_se_preciso(processo):
    """Gera o número só se a espécie gera relatório e o processo ainda não tem.

    Não grava o processo: o chamador inclui `numero_relatorio` no save.
    """
    if getattr(processo, 'sem_relatorio', False):
        return False
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


def registrar(processo):
    """Cria ou atualiza a linha da planilha a partir do processo.

    Se o número informado já existir em uma linha cancelada (verde/vermelha)
    da mesma sequência, essa linha é reaproveitada e volta ao normal.
    """
    sem_relatorio = bool(getattr(processo, 'sem_relatorio', False))
    if not processo.numero_relatorio and not sem_relatorio:
        return None
    dados = _dados_da_linha(processo)
    dados['sem_relatorio'] = sem_relatorio
    dados['situacao_linha'] = LinhaControleRelatorio.SITUACAO_ATIVA

    numero_txt = str(processo.numero_relatorio or '').strip()
    sequencia = sequencia_do_processo(processo) or GRUPO_PADRAO
    reaproveitar = None
    if numero_txt and not sem_relatorio:
        reaproveitar = (
            LinhaControleRelatorio.objects
            .filter(filtro_sequencia(sequencia), numero_relatorio=numero_txt)
            .filter(situacao_linha__in=[
                LinhaControleRelatorio.SITUACAO_RESERVADA,
                LinhaControleRelatorio.SITUACAO_CANCELADA,
            ])
            .order_by('-atualizado_em', '-id')
            .first()
        )

    if reaproveitar is not None:
        antiga = LinhaControleRelatorio.objects.filter(processo=processo).first()
        if antiga is not None and antiga.id != reaproveitar.id:
            antiga.delete()
        for campo, valor in dados.items():
            setattr(reaproveitar, campo, valor)
        reaproveitar.processo = processo
        reaproveitar.situacao_linha = LinhaControleRelatorio.SITUACAO_ATIVA
        obs = (reaproveitar.observacao or '').strip()
        if obs.startswith('Relatório cancelado'):
            reaproveitar.observacao = processo.observacao or ''
        reaproveitar.save()
        return reaproveitar

    linha, _ = LinhaControleRelatorio.objects.update_or_create(
        processo=processo, defaults=dados)
    return linha


@transaction.atomic
def cancelar_linha(usuario, linha_id, destino_numero):
    """Cancela a linha na planilha, mantendo número e data.

    destino_numero:
      - 'guardar': número fica reservado (linha verde)
      - 'excluir': número sai da sequência (linha vermelha)
    """
    perm.assert_permissao(
        perm.pode_cancelar_linha_relatorio(usuario),
        'Somente analista de Liquidações, a Gestão e o administrador '
        'cancelam linha no Controle de relatório.')
    linha = (LinhaControleRelatorio.objects
             .select_for_update()
             .select_related('processo')
             .filter(id=linha_id)
             .first())
    if linha is None:
        raise RelatorioInvalido('Linha não encontrada.')
    if linha.situacao_linha != LinhaControleRelatorio.SITUACAO_ATIVA:
        raise RelatorioInvalido('Esta linha já foi cancelada.')
    if not linha.numero_relatorio and not linha.sem_relatorio:
        raise RelatorioInvalido('Não há número de relatório nesta linha.')

    destino = (destino_numero or '').strip().lower()
    if destino in ('guardar', 'reservar', 'reserva'):
        situacao = LinhaControleRelatorio.SITUACAO_RESERVADA
    elif destino in ('excluir', 'cancelar', 'excluir_sequencia'):
        situacao = LinhaControleRelatorio.SITUACAO_CANCELADA
    else:
        raise RelatorioInvalido(
            'Escolha se o número será guardado ou excluído da sequência.')

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

    linha.processo = None
    linha.situacao_linha = situacao
    if not linha.observacao:
        if situacao == LinhaControleRelatorio.SITUACAO_RESERVADA:
            linha.observacao = 'Relatório cancelado — número guardado.'
        else:
            linha.observacao = 'Relatório cancelado — número excluído da sequência.'
    linha.save(update_fields=[
        'processo', 'situacao_linha', 'observacao', 'atualizado_em'])
    return linha


@transaction.atomic
def remover_do_processo(processo):
    """Desvincula a linha. Se era o último número emitido, o contador volta.

    Não deixa o número antigo solto para ser reaproveitado no meio da
    sequência — o próximo automático continua no contador.
    """
    linhas = list(LinhaControleRelatorio.objects.filter(processo=processo))
    for linha in linhas:
        if linha.situacao_linha != LinhaControleRelatorio.SITUACAO_ATIVA:
            continue
        numero = _inteiro(linha.numero_relatorio)
        sequencia = (linha.sequencia or '').strip() or GRUPO_PADRAO
        if numero:
            seq = (SequenciaRelatorio.objects
                   .select_for_update()
                   .filter(grupo=sequencia)
                   .first())
            if seq and int(seq.proximo_numero or 0) == numero + 1:
                seq.proximo_numero = numero
                seq.save(update_fields=['proximo_numero'])
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
                    ])
                )
                .select_related('processo'))
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
        numero_ordem=Case(
            When(numero_relatorio='', then=Value(None)),
            default=Cast('numero_relatorio', IntegerField()),
            output_field=IntegerField(null=True),
        )
    ).order_by(F('numero_ordem').asc(nulls_last=True), 'id')


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
