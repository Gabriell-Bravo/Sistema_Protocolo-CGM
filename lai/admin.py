from django.contrib import admin
from .models import Secretaria, Operador, PoliticaPrazo, ModeloMemorando

# Dados operacionais e auditoria não são editáveis pelo admin genérico.
@admin.register(Secretaria, Operador, PoliticaPrazo, ModeloMemorando)
class CadastroAdmin(admin.ModelAdmin):
    def has_delete_permission(self, request, obj=None): return False
