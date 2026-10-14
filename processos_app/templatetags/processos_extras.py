from django import template

from processos_app.services.diligencia_texto import separar_itens

register = template.Library()


@register.filter
def itens_diligencia(texto):
    return separar_itens(texto)
