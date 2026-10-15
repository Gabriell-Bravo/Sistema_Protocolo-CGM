from django import template

from processos_app.services.diligencia_texto import separar_itens

register = template.Library()

# Ícone e frase curta de cada ato. O balão da linha do tempo usa os dois.
_EVENTOS = {
    'PROCESSO_CADASTRADO': (
        'note_add', 'O processo foi cadastrado e entrou na CGM.'),
    'PROCESSO_ASSUMIDO': (
        'person_check', 'Um analista assumiu o processo para analisar.'),
    'ANALISE_DECLINADA': (
        'person_cancel', 'O analista devolveu o processo sem concluir a análise.'),
    'ASSINATURA_DIRECIONADA': (
        'draw', 'A assinatura foi encaminhada a alguém.'),
    'ASSINATURA_REDIRECIONADA': (
        'redo', 'A assinatura mudou de destinatário.'),
    'LIBERADO_ASSINATURA': (
        'verified', 'A análise foi liberada para o Controlador assinar.'),
    'DISPONIVEL_RETIRADA': (
        'inventory_2', 'O processo ficou disponível para a secretaria retirar.'),
    'DESTINO_ALTERADO': (
        'alt_route', 'O destino da saída foi alterado.'),
    'SAIDA_CONCLUIDA': (
        'logout', 'A saída da CGM foi registrada.'),
    'PRIORIDADE_ALTERADA': (
        'priority_high', 'A prioridade do processo mudou.'),
    'PROCESSO_CANCELADO': (
        'block', 'O processo foi cancelado. O registro permanece.'),
    'TRAMITE_DESFEITO': (
        'undo', 'Um passo da tramitação foi desfeito.'),
    'DEVOLVIDO_PELA_GESTAO': (
        'keyboard_return', 'A Gestão devolveu o processo.'),
    'ARQUIVO_ANEXADO': (
        'attach_file', 'Um arquivo foi anexado ao processo.'),
    'ARQUIVO_REMOVIDO': (
        'link_off', 'Um arquivo deixou de constar no processo.'),
}


@register.filter
def itens_diligencia(texto):
    return separar_itens(texto)


@register.filter
def icone_evento(tipo):
    return _EVENTOS.get(tipo, ('radio_button_checked', ''))[0]


@register.filter
def dica_evento(tipo):
    return _EVENTOS.get(tipo, ('', 'Ato registrado na tramitação.'))[1]
