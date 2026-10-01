# processos_app/services/secretaria_cgm.py
"""Processos isolados na aba Processos CGM.

Inclui:
- secretaria Controladoria Geral do Município
- espécie Contabilidade (grupo próprio, fora das filas de análise)

Ficam fora das filas e listas comuns. Só Protocolo, Gestão e o
administrador veem a aba Processos CGM.
"""

from django.db.models import Q

from . import permissions as perm

SECRETARIA_CGM = 'Controladoria Geral do Município'
GRUPO_CONTABILIDADE = 'CONTABILIDADE'
ESPECIE_CONTABILIDADE = 'Contabilidade'


def _chave(texto):
    return (texto or '').strip().casefold()


def eh_secretaria_cgm(nome):
    return _chave(nome) == _chave(SECRETARIA_CGM)


def eh_contabilidade(processo):
    if processo is None:
        return False
    if getattr(processo, 'especie_fk_id', None) and processo.especie_fk:
        if processo.especie_fk.grupo == GRUPO_CONTABILIDADE:
            return True
        if _chave(processo.especie_fk.nome) == _chave(ESPECIE_CONTABILIDADE):
            return True
    if getattr(processo, 'genero', None) == GRUPO_CONTABILIDADE:
        return True
    return _chave(getattr(processo, 'especie', None)) == _chave(ESPECIE_CONTABILIDADE)


def processo_e_da_cgm(processo):
    if processo is None:
        return False
    if eh_contabilidade(processo):
        return True
    if getattr(processo, 'secretaria_fk_id', None) and processo.secretaria_fk:
        if eh_secretaria_cgm(processo.secretaria_fk.nome):
            return True
    return eh_secretaria_cgm(processo.secretaria)


def q_processos_cgm():
    return (
        Q(secretaria__iexact=SECRETARIA_CGM) |
        Q(secretaria_fk__nome__iexact=SECRETARIA_CGM) |
        Q(genero=GRUPO_CONTABILIDADE) |
        Q(especie__iexact=ESPECIE_CONTABILIDADE) |
        Q(especie_fk__nome__iexact=ESPECIE_CONTABILIDADE) |
        Q(especie_fk__grupo=GRUPO_CONTABILIDADE)
    )


def excluir_processos_cgm(queryset):
    return queryset.exclude(q_processos_cgm())


def apenas_processos_cgm(queryset):
    return queryset.filter(q_processos_cgm())


def pode_ver_processos_cgm(user):
    return (perm.is_protocolo(user)
            or perm.is_gestao(user)
            or perm.eh_administrador(user))
