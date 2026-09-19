# processos_app/services/gestao_pessoas.py
"""
Gestão de Pessoas CGM (itens 23 e 24).

Finalidade estritamente operacional: a Gestão saber a disponibilidade real
da equipe da Controladoria e essa informação alimentar as demais telas.
NÃO é sistema de Recursos Humanos, folha de pagamento ou gestão funcional.

Regra que atravessa o módulo (itens 9 e 24): indisponibilidade é
INFORMAÇÃO, não bloqueio. Nenhuma operação do sistema é impedida por ela.
"""

from datetime import date

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from ..models import Indisponibilidade, TipoIndisponibilidade
from . import permissions as perm

DISPONIVEL = 'Disponível'


class RegistroInvalido(ValidationError):
    """Dados de indisponibilidade inconsistentes."""


# --------------------------------------------------------------------------
# Consulta de disponibilidade
# --------------------------------------------------------------------------

def indisponibilidades_em(usuario, dia=None):
    """Registros ativos que valem para este servidor nesta data."""
    dia = dia or timezone.localdate()
    candidatos = (Indisponibilidade.objects
                  .filter(usuario=usuario, ativo=True)
                  .select_related('tipo'))
    return [registro for registro in candidatos if registro.vale_em(dia)]


def esta_disponivel(usuario, dia=None):
    return not indisponibilidades_em(usuario, dia)


def rotulo_disponibilidade(usuario, dia=None):
    """Texto curto, como no documento: 'Disponível', 'Curso hoje',
    'Férias efetivamente usufruídas até 30/09'."""
    dia = dia or timezone.localdate()
    registros = indisponibilidades_em(usuario, dia)
    if not registros:
        return DISPONIVEL
    return registros[0].descricao_para(dia)


def mapa_disponibilidade(usuarios, dia=None):
    """{user_id: rótulo} em uma só consulta — para listas e quadros.

    Evita uma consulta por servidor no seletor de direcionamento e no
    quadro da equipe.
    """
    dia = dia or timezone.localdate()
    usuarios = list(usuarios)
    mapa = {u.id: DISPONIVEL for u in usuarios}
    if not usuarios:
        return mapa
    registros = (Indisponibilidade.objects
                 .filter(usuario_id__in=list(mapa), ativo=True)
                 .select_related('tipo')
                 .order_by('data_inicio', 'id'))
    for registro in registros:
        if mapa.get(registro.usuario_id) == DISPONIVEL and registro.vale_em(dia):
            mapa[registro.usuario_id] = registro.descricao_para(dia)
    return mapa


# --------------------------------------------------------------------------
# Registro — só a Gestão administra (item 23)
# --------------------------------------------------------------------------

@transaction.atomic
def registrar(autor, usuario_id, tipo_id, *, data_inicio=None, data_fim=None,
              recorrente=False, dia_semana=None, vigencia_inicio=None,
              vigencia_fim=None, observacao=''):
    """Cria um registro. Cobre dia único, período, recorrência e
    recorrência com vigência."""
    perm.assert_permissao(
        perm.pode_gerir_pessoas(autor),
        'Somente a Gestão administra a Gestão de Pessoas CGM.')

    servidor = User.objects.filter(id=usuario_id, is_active=True).first()
    if servidor is None:
        raise RegistroInvalido('Servidor não encontrado ou inativo.')

    tipo = TipoIndisponibilidade.objects.filter(id=tipo_id, ativo=True).first()
    if tipo is None:
        raise RegistroInvalido('Tipo de indisponibilidade inválido ou inativo.')

    if recorrente:
        if dia_semana in (None, ''):
            raise RegistroInvalido('Informe o dia da semana da recorrência.')
        try:
            dia_semana = int(dia_semana)
        except (TypeError, ValueError):
            raise RegistroInvalido('Dia da semana inválido.')
        if dia_semana not in dict(Indisponibilidade.DIAS_SEMANA):
            raise RegistroInvalido('Dia da semana inválido.')
        if vigencia_inicio and vigencia_fim and vigencia_fim < vigencia_inicio:
            raise RegistroInvalido('A vigência termina antes de começar.')
        data_inicio = data_fim = None
    else:
        if not data_inicio:
            raise RegistroInvalido('Informe a data de início.')
        data_fim = data_fim or data_inicio   # dia único
        if data_fim < data_inicio:
            raise RegistroInvalido('A data final é anterior à inicial.')
        dia_semana = None
        vigencia_inicio = vigencia_fim = None

    return Indisponibilidade.objects.create(
        usuario=servidor, tipo=tipo,
        data_inicio=data_inicio, data_fim=data_fim,
        recorrente=bool(recorrente), dia_semana=dia_semana,
        vigencia_inicio=vigencia_inicio, vigencia_fim=vigencia_fim,
        observacao=(observacao or '').strip(),
        criado_por=autor,
    )


@transaction.atomic
def desativar(autor, registro_id):
    """Retira o registro de circulação sem apagá-lo."""
    perm.assert_permissao(
        perm.pode_gerir_pessoas(autor),
        'Somente a Gestão administra a Gestão de Pessoas CGM.')
    registro = Indisponibilidade.objects.filter(id=registro_id).first()
    if registro is None:
        raise RegistroInvalido('Registro não encontrado.')
    registro.ativo = False
    registro.save(update_fields=['ativo'])
    return registro


def registros(apenas_ativos=True):
    consulta = (Indisponibilidade.objects
                .select_related('usuario', 'tipo', 'criado_por')
                .order_by('-criado_em'))
    if apenas_ativos:
        consulta = consulta.filter(ativo=True)
    return consulta


def servidores():
    """Toda a equipe ativa: Protocolo e Gestão também têm férias e curso."""
    return (User.objects.filter(is_active=True)
            .select_related('profile')
            .order_by('first_name', 'username'))


def converter_data(texto):
    """'AAAA-MM-DD' -> date, ou None. Entrada inválida vira None."""
    texto = (texto or '').strip()
    if not texto:
        return None
    try:
        return date.fromisoformat(texto)
    except ValueError:
        return None
