# processos_app/services/relatorios.py
"""Controle de relatório: sequência numérica e planilha das análises.

O administrador informa o último número já usado. O próximo processo
assumido (espécie que gera relatório) recebe o seguinte.

Cada assunção grava uma linha na planilha. Salvar a análise atualiza
os demais campos. Declinar desvincula a linha, mas o número não volta
a ser usado.
"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from ..models import LinhaControleRelatorio, SequenciaRelatorio
from . import permissions as perm


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
    return estado_sequencia(grupo)


def registrar(processo):
    """Cria ou atualiza a linha da planilha a partir do processo."""
    if not processo.numero_relatorio:
        return None
    dados = _dados_da_linha(processo)
    linha, _ = LinhaControleRelatorio.objects.update_or_create(
        processo=processo, defaults=dados)
    return linha


def remover_do_processo(processo):
    """Desvincula a linha. O número permanece reservado e não é reemitido."""
    LinhaControleRelatorio.objects.filter(processo=processo).update(processo=None)


def listar(usuario):
    consulta = LinhaControleRelatorio.objects.filter(processo__isnull=False)
    if perm.eh_administrador(usuario) or perm.is_gestao(usuario):
        return consulta
    if perm.is_analista(usuario):
        grupo = perm.grupo_do_analista(usuario)
        if grupo:
            return consulta.filter(grupo=grupo)
        return consulta.none()
    return consulta.none()


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
