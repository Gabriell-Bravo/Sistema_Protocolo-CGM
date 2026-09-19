# processos_app/services/monitoramento.py
"""
Monitoramento (itens 41 a 44).

Corrige três problemas do comportamento anterior:

  1. Períodos reais de calendário com `relativedelta` (item 41). Antes,
     "6 meses" era `timedelta(days=180)`: 31/08 + 180 dias = 27/02, quando o
     correto é 28/02 (ou 29/02 em ano bissexto).
  2. A periodicidade vem da ESPÉCIE cadastrada (item 42). Antes, a mesma
     regra estava repetida em salvar_processo, atualizar_processo e no
     JavaScript do formulário — e as três versões divergiam.
  3. Concluir monitoramento NÃO registra saída física (item 44), e abrir uma
     página não grava nada (item 43): o status "Atrasado" é calculado na
     exibição. Quem quiser o campo persistido roda o comando
     `atualizar_status_monitoramento` em agendamento (cron).
"""

from dateutil.relativedelta import relativedelta
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from ..models import EspecieProcesso, MonitoramentoRecord, Processo
from . import cadastros
from . import permissions as perm
from .eventos import registrar_diff

NAO_APLICAVEL = 'NAO_APLICAVEL'
STATUS_ABERTOS = ('PENDENTE', 'ATRASADO')


# --------------------------------------------------------------------------
# Regra
# --------------------------------------------------------------------------

def especie_do_processo(processo):
    """Cadastro da espécie: o vínculo gravado ou, para registro antigo, a
    resolução pelo texto."""
    if processo.especie_fk_id:
        return processo.especie_fk
    return cadastros.resolver_especie(processo.especie, processo.genero)


def tipo_do_processo(processo):
    """Periodicidade aplicável ao processo, ou None."""
    especie = especie_do_processo(processo)
    if especie is None or especie.tipo_monitoramento == 'NENHUM':
        return None
    return especie.tipo_monitoramento


def somar_periodo(data_base, tipo):
    """Soma o período em meses de calendário (item 41)."""
    meses = EspecieProcesso.MESES_POR_TIPO.get(tipo or '')
    if not data_base or not meses:
        return None
    return data_base + relativedelta(months=meses)


def definir_inicial(processo, data_base=None):
    """Preenche (em memória) os campos de monitoramento de um processo
    recém-criado. Quem chama salva."""
    tipo = tipo_do_processo(processo)
    if tipo is None:
        processo.prazo_monitoramento = NAO_APLICAVEL
        processo.status_monitoramento = NAO_APLICAVEL
        processo.proxima_data_monitoramento = None
        return processo
    base = data_base or processo.data_saida or processo.data_entrada
    processo.prazo_monitoramento = tipo
    processo.status_monitoramento = 'PENDENTE'
    processo.proxima_data_monitoramento = somar_periodo(base, tipo)
    return processo


CAMPOS_DA_ESPECIE = {'especie', 'especie_fk', 'genero'}


def recalcular_apos_edicao(processo, campos_alterados):
    """Reavalia o monitoramento depois de uma edição de protocolo.

    Só recalcula quando a edição muda a regra (espécie/grupo) ou a data-base
    (data de entrada). Corrige um defeito do código anterior: qualquer
    edição de um processo com monitoramento CONCLUÍDO o reabria como
    PENDENTE, porque a conclusão grava periodicidade "Não aplicável".
    """
    alterados = set(campos_alterados)
    mudou_especie = bool(CAMPOS_DA_ESPECIE & alterados)
    if not (mudou_especie or 'data_entrada' in alterados):
        return False
    if processo.status_monitoramento == 'CONCLUIDO' and not mudou_especie:
        return False   # corrigir a data de entrada não reabre ciclo encerrado

    tipo = tipo_do_processo(processo)
    if tipo is None:
        processo.prazo_monitoramento = NAO_APLICAVEL
        processo.status_monitoramento = NAO_APLICAVEL
        processo.proxima_data_monitoramento = None
        return True
    processo.prazo_monitoramento = tipo
    if processo.status_monitoramento in (NAO_APLICAVEL, 'CONCLUIDO', None, ''):
        processo.status_monitoramento = 'PENDENTE'
    base = processo.data_saida or processo.data_entrada
    processo.proxima_data_monitoramento = somar_periodo(base, tipo)
    return True


def encerrar_ciclos_anteriores(processo, usuario):
    """A entrada de uma espécie que "encerra monitoramento anterior" conclui
    o monitoramento pendente das passagens anteriores do mesmo número.

    Preserva a regra que estava em salvar_processo: só participam do ciclo
    as espécies marcadas no cadastro.
    """
    especie = especie_do_processo(processo)
    if especie is None or not especie.encerra_monitoramento_anterior:
        return 0
    nomes_do_ciclo = set(EspecieProcesso.objects
                         .filter(encerra_monitoramento_anterior=True)
                         .values_list('nome', flat=True))
    anteriores = (Processo.objects
                  .filter(numero_processo=processo.numero_processo,
                          status_monitoramento__in=STATUS_ABERTOS)
                  .filter(Q(especie_fk__encerra_monitoramento_anterior=True)
                          | Q(especie__in=nomes_do_ciclo))
                  .exclude(id=processo.id))
    total = 0
    for anterior in anteriores:
        _encerrar(anterior, usuario,
                  f'Monitoramento concluído automaticamente pela entrada de '
                  f'nova passagem do processo {processo.numero_processo} '
                  f'({especie.nome}).')
        total += 1
    return total


# --------------------------------------------------------------------------
# Status calculado (item 43 — GET não grava)
# --------------------------------------------------------------------------

def status_efetivo(processo, referencia=None):
    """Status que a tela deve mostrar hoje, sem alterar o banco.

    Reproduz as duas regras que antes eram GRAVADAS ao abrir a lista de
    finalizados: PENDENTE vencido aparece como ATRASADO; CONCLUIDO com nova
    data já alcançada volta a aparecer como PENDENTE.
    """
    hoje = referencia or timezone.localdate()
    status = processo.status_monitoramento
    data = processo.proxima_data_monitoramento
    if status in ('PENDENTE', 'CONCLUIDO') and data and data < hoje:
        # Ciclo vencido — inclusive o reaberto cuja data já passou.
        return 'ATRASADO'
    if status == 'CONCLUIDO' and data and data == hoje:
        return 'PENDENTE'
    return status


ROTULOS_STATUS = dict(Processo.STATUS_MONITORAMENTO_CHOICES)


def filtro_status(status, referencia=None):
    """Q equivalente a `status_efetivo == status`, para filtrar no banco."""
    hoje = referencia or timezone.localdate()
    atrasado = Q(status_monitoramento='ATRASADO') | Q(
        status_monitoramento__in=['PENDENTE', 'CONCLUIDO'],
        proxima_data_monitoramento__lt=hoje)
    reaberto_hoje = Q(status_monitoramento='CONCLUIDO',
                      proxima_data_monitoramento=hoje)
    if status == 'ATRASADO':
        return atrasado
    if status == 'PENDENTE':
        return (Q(status_monitoramento='PENDENTE') & ~atrasado) | reaberto_hoje
    if status == 'CONCLUIDO':
        return (Q(status_monitoramento='CONCLUIDO')
                & ~Q(proxima_data_monitoramento__lte=hoje))
    return Q(status_monitoramento=status)


# --------------------------------------------------------------------------
# Ações
# --------------------------------------------------------------------------

def pode_concluir(usuario, processo):
    """Mantém quem já podia concluir: analista do grupo e Gestão."""
    return perm.is_gestao(usuario) or (
        perm.is_analista(usuario) and perm.pode_ver_grupo(usuario, processo.genero))


@transaction.atomic
def concluir(processo_id, usuario):
    """Conclui o monitoramento. NÃO toca em saída física (item 44):
    situacao_tramite, data_saida e saida_concluida_* ficam como estão."""
    processo = (Processo.objects.select_for_update()
                .filter(id=processo_id).first())
    if processo is None:
        raise ValidationError('Processo não encontrado.')
    perm.assert_permissao(
        pode_concluir(usuario, processo),
        'Você não tem permissão para concluir o monitoramento deste processo.')
    _encerrar(processo, usuario,
              f'Monitoramento concluído manualmente por {perm.nome_usuario(usuario)}.')
    return processo


def _encerrar(processo, usuario, observacao):
    anterior = processo.status_monitoramento
    processo.status_monitoramento = 'CONCLUIDO'
    processo.proxima_data_monitoramento = None
    processo.prazo_monitoramento = NAO_APLICAVEL
    processo.save(update_fields=['status_monitoramento',
                                 'proxima_data_monitoramento',
                                 'prazo_monitoramento'])
    MonitoramentoRecord.objects.create(
        processo=processo, observacao=observacao,
        registrado_por=usuario if (usuario and usuario.is_authenticated) else None)
    registrar_diff(processo, 'status_monitoramento', anterior, 'CONCLUIDO', usuario)


def persistir_status(referencia=None):
    """Grava o status calculado. Uso exclusivo do comando agendado —
    nunca de uma view GET (item 43). Devolve {status: quantidade}."""
    hoje = referencia or timezone.localdate()
    # Mesma regra de status_efetivo(): data de hoje reabre (PENDENTE);
    # data passada é ATRASADO, tenha o ciclo anterior sido concluído ou não.
    reabertos = (Processo.objects
                 .filter(status_monitoramento='CONCLUIDO',
                         proxima_data_monitoramento=hoje)
                 .update(status_monitoramento='PENDENTE'))
    atrasados = (Processo.objects
                 .filter(status_monitoramento__in=['PENDENTE', 'CONCLUIDO'],
                         proxima_data_monitoramento__lt=hoje)
                 .update(status_monitoramento='ATRASADO'))
    return {'ATRASADO': atrasados, 'PENDENTE': reabertos}
