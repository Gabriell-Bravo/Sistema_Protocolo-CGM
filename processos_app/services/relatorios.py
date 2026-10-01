# processos_app/services/relatorios.py
"""Controle de relatório: sequência numérica e planilha das análises.

O administrador informa o último número já usado. O número é gerado
quando o analista salva a análise. Correções da análise saem pelo lápis
da planilha, na tela do processo. O administrador também corrige o
número, mesmo já emitido.

A geração automática não repete um número que ainda está numa análise.
Declinar devolve o número: o próximo salvamento usa esse, não o seguinte.
"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import IntegerField
from django.db.models.functions import Cast
from django.utils import timezone

from ..models import LinhaControleRelatorio, Processo, SequenciaRelatorio
from . import permissions as perm
from .eventos import registrar_diff


GRUPO_PADRAO = perm.GRUPO_LIQUIDACOES


class RelatorioInvalido(ValidationError):
    """Dados recusados no controle de relatório."""


def estado_sequencia(grupo=GRUPO_PADRAO):
    seq = SequenciaRelatorio.objects.filter(grupo=grupo).first()
    proximo = seq.proximo_numero if seq else 1540
    return {
        'grupo': grupo,
        'proximo': proximo,
        'ultimo': max(proximo - 1, 0),
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


def numeros_usados(grupo, ignorar=None):
    """Números ainda presos a uma análise. Linha desvinculada está livre."""
    ignorar = set(ignorar or ())
    usados = set()
    fontes = (
        Processo.objects.filter(genero=grupo)
            .exclude(numero_relatorio__isnull=True)
            .exclude(numero_relatorio='')
            .values_list('numero_relatorio', flat=True),
        LinhaControleRelatorio.objects.filter(grupo=grupo, processo__isnull=False)
            .exclude(numero_relatorio='')
            .values_list('numero_relatorio', flat=True),
    )
    for lista in fontes:
        for bruto in lista:
            numero = _inteiro(bruto)
            if numero:
                usados.add(numero)
    return usados - ignorar


def _numeros_devolvidos(grupo, usados):
    """Números de análises desistidas, ainda não reaproveitados."""
    livres = []
    for bruto in (LinhaControleRelatorio.objects
                  .filter(grupo=grupo, processo__isnull=True)
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
        grupo=grupo, processo__isnull=True).delete()
    return estado_sequencia(grupo)


def proximo_numero(grupo):
    """Trava a sequência para dois salvamentos não saírem iguais."""
    SequenciaRelatorio.objects.get_or_create(
        grupo=grupo, defaults={'proximo_numero': 1540})
    seq = SequenciaRelatorio.objects.select_for_update().get(grupo=grupo)
    usados = numeros_usados(grupo)
    livres = _numeros_devolvidos(grupo, usados)
    if livres:
        numero = min(livres)
        LinhaControleRelatorio.objects.filter(
            grupo=grupo, processo__isnull=True, numero_relatorio=str(numero)
        ).delete()
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
    processo.numero_relatorio = proximo_numero(processo.genero)
    registrar(processo)
    return True


def _inteiro_atual(processo):
    try:
        return int(str(processo.numero_relatorio).strip())
    except (TypeError, ValueError):
        return None


@transaction.atomic
def alterar_numero(usuario, processo_id, novo):
    """Administrador grava o número que quiser numa análise já feita."""
    processo = (Processo.objects.select_for_update()
                .filter(id=processo_id).first())
    if processo is None:
        raise RelatorioInvalido('Processo não encontrado.')
    perm.assert_permissao(
        perm.pode_editar_numero_relatorio(usuario),
        'Somente o administrador altera o número de relatório.')
    if not processo.numero_relatorio:
        raise RelatorioInvalido(
            'O número só pode ser alterado depois de salvar a análise.')
    try:
        novo = int(str(novo).strip())
    except (TypeError, ValueError):
        raise RelatorioInvalido('Informe um número inteiro para o relatório.')
    if novo < 1:
        raise RelatorioInvalido('O número do relatório deve ser maior que zero.')

    atual = _inteiro_atual(processo)
    if atual == novo:
        return processo

    anterior = processo.numero_relatorio or ''
    processo.numero_relatorio = str(novo)
    processo.save(update_fields=['numero_relatorio'])
    registrar(processo)

    seq, _ = SequenciaRelatorio.objects.select_for_update().get_or_create(
        grupo=processo.genero or GRUPO_PADRAO,
        defaults={'proximo_numero': novo + 1})
    if int(seq.proximo_numero or 0) <= novo:
        seq.proximo_numero = novo + 1
        seq.save(update_fields=['proximo_numero'])

    registrar_diff(processo, 'numero_relatorio', anterior, str(novo), usuario)
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


def listar(usuario):
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
    return consulta.annotate(
        numero_ordem=Cast('numero_relatorio', IntegerField())
    ).order_by('numero_ordem', 'id')


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
    }
