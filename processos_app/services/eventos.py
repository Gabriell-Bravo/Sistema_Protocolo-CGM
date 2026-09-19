# processos_app/services/eventos.py
"""
Registro do histórico de atos administrativos (itens 45 e 46).

Princípio central (item 1): usuário, data e hora nunca são perguntados.
Vêm de request.user e timezone.now().
"""

from ..models import EventoProcesso, EventoPendencia, ProcessHistory


def registrar_evento(processo, tipo, usuario=None, descricao='', **dados):
    """Grava um EventoProcesso.

    `dados` aceita qualquer par chave/valor serializável em JSON — é onde
    ficam destino anterior, novo destino, autorizado por, etc.
    """
    return EventoProcesso.objects.create(
        processo=processo,
        tipo=tipo,
        usuario=usuario if (usuario and usuario.is_authenticated) else None,
        descricao=descricao,
        dados={k: _serializavel(v) for k, v in dados.items()},
    )


def registrar_evento_pendencia(pendencia, tipo, usuario=None, descricao=''):
    """Grava um EventoPendencia (item 46).

    Apenas os cinco atos formais. Telefonema, e-mail, WhatsApp e cobrança
    intermediária não são registrados (item 25).
    """
    return EventoPendencia.objects.create(
        pendencia=pendencia,
        tipo=tipo,
        usuario=usuario if (usuario and usuario.is_authenticated) else None,
        descricao=descricao,
    )


def registrar_diff(processo, campo, anterior, novo, usuario=None):
    """Mantém o ProcessHistory campo-a-campo já existente.

    As duas fontes convivem: ProcessHistory mostra o que mudou no registro,
    EventoProcesso mostra o ato praticado.
    """
    return ProcessHistory.objects.create(
        process=processo,
        field_name=campo,
        old_value='' if anterior is None else str(anterior),
        new_value='' if novo is None else str(novo),
        changed_by=usuario if (usuario and usuario.is_authenticated) else None,
    )


def linha_do_tempo(processo):
    """Eventos e diffs do processo, em ordem decrescente, para a tela de
    histórico."""
    itens = []
    for evento in processo.eventos.select_related('usuario'):
        itens.append({
            'quando': evento.criado_em,
            'tipo': 'evento',
            'titulo': evento.get_tipo_display(),
            'detalhe': evento.descricao,
            'usuario': evento.usuario,
            'dados': evento.dados,
        })
    for diff in ProcessHistory.objects.filter(
            process=processo).select_related('changed_by'):
        itens.append({
            'quando': diff.changed_at,
            'tipo': 'campo',
            'titulo': diff.field_name,
            'detalhe': f'{diff.old_value} → {diff.new_value}',
            'usuario': diff.changed_by,
            'dados': {},
        })
    itens.sort(key=lambda i: i['quando'], reverse=True)
    return itens


def _serializavel(valor):
    if valor is None or isinstance(valor, (str, int, float, bool)):
        return valor
    return str(valor)
