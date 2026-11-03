"""Contagem local versionada; a data externa validada nunca é sobrescrita."""
from datetime import timedelta

def util(data, politica):
    return data.weekday() < 5 and data.isoformat() not in politica.feriados

def somar(base, dias, politica):
    data = base
    for _ in range(dias):
        data += timedelta(days=1)
        while politica.dias_uteis and not util(data, politica): data += timedelta(days=1)
    while politica.ajustar_vencimento and not util(data, politica): data += timedelta(days=1)
    return data

def marco(d, hoje):
    if d.encerrada or not d.conferido_em: return None
    p = d.politica
    venc = d.vencimento
    if hoje > venc: return ('ATRASO', 'vermelho', 'Prazo externo vencido — resposta final pendente')
    if not d.precisa_resposta_interna:
        if hoje >= venc - timedelta(days=2):
            return ('FINAL', 'vermelho', 'Registrar resposta final no Fala.BR')
        return None
    if d.prorrogacoes.exists():
        limite = min(somar(d.vencimento_original, p.alerta_prorrogacao, p), venc - timedelta(days=2))
        if hoje >= limite: return ('P8', 'vermelho', 'Prorrogação próxima do vencimento — cobrar resposta')
        return ('PRORROGADA', 'amarelo', 'Prazo prorrogado — acompanhamento de risco')
    if hoje >= min(somar(d.marco_inicial, p.alerta_urgente, p), venc - timedelta(days=1)):
        return ('D19', 'laranja', 'Risco de descumprimento — avaliar prorrogação formal')
    if hoje >= somar(d.marco_inicial, p.alerta_inicial, p):
        return ('D10', 'amarelo', 'Primeira cobrança — resposta da secretaria pendente')
    return None
