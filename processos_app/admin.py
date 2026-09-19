"""Admin do Django — apenas apoio ao TI.

A operação do dia a dia (cadastros, usuários, gestão de pessoas) é feita
pelas telas do sistema, que aplicam as regras de negócio. Processo NÃO é
registrado aqui de propósito: editar pelo admin pularia a máquina de
estados, o histórico e as permissões por papel.
"""

from django.contrib import admin

from .models import (EspecieProcesso, Indisponibilidade, Prioridade, Profile,
                     TipoIndisponibilidade, UnidadeAdministrativa)


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'papel', 'level')
    list_filter = ('papel',)
    search_fields = ('user__username', 'user__first_name', 'user__last_name')


@admin.register(UnidadeAdministrativa)
class UnidadeAdministrativaAdmin(admin.ModelAdmin):
    list_display = ('nome', 'sigla', 'ativo', 'ordem')
    list_filter = ('ativo',)
    search_fields = ('nome', 'sigla')


@admin.register(EspecieProcesso)
class EspecieProcessoAdmin(admin.ModelAdmin):
    list_display = ('nome', 'grupo', 'tipo_monitoramento', 'gera_relatorio', 'ativo', 'ordem')
    list_filter = ('grupo', 'ativo', 'tipo_monitoramento')
    search_fields = ('nome',)


@admin.register(Prioridade)
class PrioridadeAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'nome', 'prazo_dias', 'ordem', 'ativo')


@admin.register(TipoIndisponibilidade)
class TipoIndisponibilidadeAdmin(admin.ModelAdmin):
    list_display = ('nome', 'ativo')


@admin.register(Indisponibilidade)
class IndisponibilidadeAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'tipo', 'data_inicio', 'data_fim', 'recorrente', 'ativo')
    list_filter = ('tipo', 'ativo', 'recorrente')
    readonly_fields = ('criado_em', 'criado_por')
