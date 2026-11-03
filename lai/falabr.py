"""Consulta de pedidos LAI em aberto na API Me-Ouv do Fala.BR.

O login humano do gov.br não é usado. O servidor autentica o usuário de
aplicação do órgão e pede somente a lista. Senha e segredo não saem daqui.
"""
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from django.conf import settings

SITUACOES_PENDENTES = (1, 2, 3, 4)
_cache = {'token': '', 'expira': 0.0}


class FalabrError(Exception):
    pass


def configurado():
    return all(_cfg(nome) for nome in ('CLIENT_ID', 'CLIENT_SECRET', 'USERNAME', 'PASSWORD'))


def limpar_cache():
    _cache.update(token='', expira=0.0)


def listar_pendentes():
    if not configurado():
        raise FalabrError('Usuário de aplicação do Fala.BR ainda não configurado no servidor.')
    token = _token()
    tipo = _formulario_lai(token)
    vistos = {}
    for situacao in SITUACOES_PENDENTES:
        inicio = 1
        while inicio <= 1001:
            itens = _lista(_get(token, '/api/manifestacoes', {
                'IdTipoFormulario': tipo,
                'IdSituacaoManifestacao': situacao,
                'MaxResultados': 250,
                'PosInicioPagina': inicio,
            }))
            for item in itens:
                linha = _resumir(item)
                if linha['nup_normalizada']:
                    vistos[linha['nup_normalizada']] = linha
            if len(itens) < 250:
                break
            inicio += 250
    return sorted(vistos.values(), key=lambda row: (row['prazo'] or '99', row['nup']))


def _cfg(nome):
    return str(getattr(settings, 'LAI_FALABR_' + nome, '') or '').strip()


def _base():
    return str(getattr(settings, 'LAI_FALABR_BASE', 'https://falabr.cgu.gov.br')).rstrip('/')


def _ocultar(texto):
    limpo = str(texto or '')
    for nome in ('PASSWORD', 'CLIENT_SECRET', 'CLIENT_ID', 'USERNAME'):
        segredo = _cfg(nome)
        if segredo:
            limpo = limpo.replace(segredo, '***')
    return limpo


def _mensagem(codigo, corpo):
    if codigo in (401, 400):
        return 'O Fala.BR recusou o usuário de aplicação. Confira os dados configurados no servidor.'
    if codigo == 403:
        return 'O usuário de aplicação não tem permissão para consultar as manifestações do órgão.'
    return f'O Fala.BR respondeu com erro {codigo}. {_ocultar(corpo)[:180]}'


def _abrir(req, vazio_se_404=False):
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            bruto = resp.read().decode('utf-8')
            return json.loads(bruto) if bruto else []
    except urllib.error.HTTPError as exc:
        corpo = exc.read().decode('utf-8', errors='replace')
        if exc.code == 404 and vazio_se_404:
            return []
        raise FalabrError(_mensagem(exc.code, corpo)) from None
    except urllib.error.URLError:
        raise FalabrError('Não foi possível falar com o Fala.BR. Confira a rede do servidor.') from None
    except json.JSONDecodeError:
        raise FalabrError('O Fala.BR devolveu uma resposta que não é JSON.') from None


def _token():
    agora = time.monotonic()
    if _cache['token'] and _cache['expira'] > agora:
        return _cache['token']
    corpo = urllib.parse.urlencode({
        'grant_type': 'password',
        'client_id': _cfg('CLIENT_ID'),
        'client_secret': _cfg('CLIENT_SECRET'),
        'username': _cfg('USERNAME'),
        'password': _cfg('PASSWORD'),
    }).encode()
    req = urllib.request.Request(
        _base() + '/oauth/token',
        data=corpo,
        headers={'Accept': 'application/json', 'Content-Type': 'application/x-www-form-urlencoded'},
        method='POST',
    )
    payload = _abrir(req)
    token = payload.get('access_token') if isinstance(payload, dict) else ''
    if not token:
        raise FalabrError('O Fala.BR não devolveu o token de acesso.')
    _cache.update(token=token, expira=agora + 12 * 60 * 60)
    return token


def _get(token, caminho, params=None):
    url = _base() + caminho
    if params:
        url += '?' + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={'Accept': 'application/json', 'Authorization': 'Bearer ' + token})
    return _abrir(req, vazio_se_404=caminho.startswith('/api/manifestacoes'))


def _lista(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for chave in ('value', 'Values', 'Manifestacoes', 'items'):
            if isinstance(payload.get(chave), list):
                return payload[chave]
        if 'IdManifestacao' in payload or 'NumerosProtocolo' in payload:
            return [payload]
    return []


def _formulario_lai(token):
    for item in _lista(_get(token, '/api/tipos-formulario')):
        descricao = str(item.get('DescTipoFormulario') or '').casefold()
        if 'acesso' in descricao and 'informa' in descricao:
            return item.get('IdTipoFormulario')
    raise FalabrError('A API não identificou o formulário de Acesso à Informação.')


def _resumir(item):
    numeros = [str(n).strip() for n in (item.get('NumerosProtocolo') or []) if str(n).strip()]
    nup = numeros[0] if numeros else ''
    assunto = (item.get('Assunto') or {}).get('DescAssunto') or ''
    situacao = (item.get('Situacao') or {}).get('DescSituacaoManifestacao') or ''
    return {
        'nup': nup,
        'nup_normalizada': re.sub(r'\D', '', nup),
        'assunto': assunto,
        'situacao': situacao,
        'cadastro': str(item.get('DataCadastro') or ''),
        'prazo': str(item.get('PrazoAtendimento') or ''),
    }
