"""Janela local do Fala.BR para quem já tem acesso.

A pessoa entra no gov.br numa janela comum do Edge ou do Chrome.
Este módulo não vê nem guarda a senha. O navegador automático só é
ligado depois, na hora de ler a lista de manifestações que está na tela.
O gov.br não conclui o CPF quando percebe uma janela controlada.

Da lista são lidos número, órgão, assunto, serviço, tipo, cadastro, prazo,
situação e responsável. O e-mail do manifestante aparece na tabela, mas
não é lido nem guardado.
"""
import json
import logging
import os
import re
import subprocess
import threading
import time
import unicodedata
import urllib.request
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

from django.conf import settings

log = logging.getLogger(__name__)

ENTRADA = 'https://falabr.cgu.gov.br/'
URL_LISTA = 'https://falabr.cgu.gov.br/web/manifestacao/tratar'
# Situações do Fala.BR: 1 Cadastrada, 2 Complementada, 3 Prorrogada, 4 Encaminhada por outro órgão,
# 5 Complementação solicitada; 6 Concluída, 7 Encaminhada para órgão externo (encerrada), 8 Arquivada.
GRUPOS = (('abertas', '1,2,3,4,5'), ('encerradas', '6,7,8'))
PORTA = 9333
MAX_PAGINAS = 80
_NUP = re.compile(r'\b\d{5}\.\d{6}/\d{4}-\d{2}\b|\b\d{5}\.\d{4}\.\d{6,8}-\d{2}\b')
_estado = {'fase': 'fechado', 'mensagem': ''}

# Quem está logada no Fala.BR aparece no botão do canto da tela (#avatar-sign-in): inicial, nome e perfil.
_USUARIO_JS = """() => {
    const botao = document.querySelector('#avatar-sign-in');
    if (!botao) return null;
    const partes = (botao.innerText || '').split('\\n').map(p => p.trim()).filter(p => p.length > 1);
    return {nome: partes[0] || '', perfil: partes[1] || ''};
}"""
_SESSAO_VALIDADE = 6  # segundos que uma leitura da sessão vale antes de consultar o navegador de novo
_cache_sessao = {'em': 0.0, 'valor': None}
_trava_sessao = threading.Lock()

# Colunas da lista do Fala.BR que o módulo usa. As demais são ignoradas.
_COLUNAS = {
    'numero': 'nup',
    'orgaodestinatario': 'orgao',
    'assunto': 'assunto',
    'servico': 'servico',
    'tipo': 'tipo',
    'cadastro': 'cadastro',
    'prazo': 'prazo',
    'situacao': 'situacao',
    'responsavel': 'responsavel',
}

_ACHAR_TABELA = """
const achar = () => Array.from(document.querySelectorAll('table')).find(t => {
    const cab = Array.from(t.querySelectorAll('th')).map(h => h.innerText.trim().toLowerCase());
    return cab.includes('prazo') && cab.some(c => c.startsWith('n') && c.includes('mero'));
});
"""

_LER_JS = "() => {" + _ACHAR_TABELA + """
    const t = achar();
    if (!t) return null;
    const cab = Array.from(t.querySelectorAll('th')).map(h => h.innerText.trim());
    const linhas = Array.from(t.querySelectorAll('tbody tr')).map(tr =>
        Array.from(tr.querySelectorAll('td')).map(td => {
            const a = td.querySelector('a');
            return {texto: (td.innerText || '').trim(), href: a ? a.href : ''};
        })).filter(l => l.length);
    const m = (document.body.innerText.match(/Total de registros:\\s*(\\d+)/) || [])[1];
    return {cab: cab, linhas: linhas, total: m ? parseInt(m, 10) : null};
}"""

_PRIMEIRA_JS = "() => {" + _ACHAR_TABELA + """
    const t = achar();
    const td = t && t.querySelector('tbody tr td');
    return td ? td.innerText.trim() : '';
}"""

_TROCOU_JS = "(marca) => {" + _ACHAR_TABELA + """
    const t = achar();
    const td = t && t.querySelector('tbody tr td');
    return !!td && td.innerText.trim() !== marca;
}"""

_ESTADO_JS = "() => {" + _ACHAR_TABELA + """
    const t = achar();
    if (!t) return null;
    const m = (document.body.innerText.match(/Total de registros:\\s*(\\d+)/) || [])[1];
    const linhas = Array.from(t.querySelectorAll('tbody tr')).filter(tr => tr.querySelectorAll('td').length > 3).length;
    return {total: m ? parseInt(m, 10) : null, linhas: linhas};
}"""

_PROXIMA = '[id$="pagination-arrows-right-btn"]'
_ANTERIOR = '[id$="pagination-arrows-left-btn"]'


class NavegadorError(Exception):
    pass


def protocolos_no_texto(texto):
    vistos = []
    usados = set()
    for nup in _NUP.findall(texto or ''):
        chave = re.sub(r'\D', '', nup)
        if chave in usados:
            continue
        usados.add(chave)
        vistos.append(nup)
    return vistos


def estado():
    return {'fase': _estado['fase'], 'mensagem': _estado['mensagem']}


def sessao_guardada():
    """Última leitura da sessão, sem consultar o navegador. 'verificado' é falso se nunca foi lida."""
    valor = _cache_sessao['valor']
    if valor is None:
        return {'online': False, 'nome': '', 'perfil': '', 'janela': False, 'verificado': False}
    return dict(valor, verificado=True)


def sessao(forcar=False):
    """Diz se a pessoa está online no Fala.BR: {'online', 'nome', 'perfil', 'janela'}.

    Online = a janela do módulo está aberta e uma página do Fala.BR mostra o nome de quem entrou.
    Só o nome e o perfil exibidos pelo próprio Fala.BR são lidos; senha e cookies nunca.
    A leitura vale alguns segundos, para a tela poder perguntar com frequência sem sobrecarregar.
    """
    if not _porta_responde():
        return _guardar_sessao({'online': False, 'nome': '', 'perfil': '', 'janela': False})
    valor = _cache_sessao['valor']
    if not forcar and valor is not None and valor['janela'] and time.time() - _cache_sessao['em'] < _SESSAO_VALIDADE:
        return dict(valor, verificado=True)
    if not _trava_sessao.acquire(blocking=forcar):
        return sessao_guardada()
    try:
        return _guardar_sessao(_ler_sessao())
    finally:
        _trava_sessao.release()


def _guardar_sessao(valor):
    _cache_sessao['valor'] = dict(valor)
    _cache_sessao['em'] = time.time()
    return dict(valor, verificado=True)


def _ler_sessao():
    offline = {'online': False, 'nome': '', 'perfil': '', 'janela': True}
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return offline
    try:
        with sync_playwright() as playwright:
            navegador = playwright.chromium.connect_over_cdp(_endereco_cdp())
            for contexto in navegador.contexts:
                for pagina in contexto.pages:
                    if 'falabr.cgu.gov.br' not in (pagina.url or ''):
                        continue
                    try:
                        usuario = pagina.evaluate(_USUARIO_JS)
                    except Exception:
                        continue
                    if usuario and usuario.get('nome'):
                        return {'online': True, 'nome': usuario['nome'], 'perfil': usuario.get('perfil', ''), 'janela': True}
    except Exception as exc:
        log.warning('Não foi possível conferir o login no Fala.BR: %s', exc)
        anterior = _cache_sessao['valor']
        # Uma falha passageira (página trocando) não derruba quem estava online.
        return dict(anterior) if anterior and anterior.get('online') else offline
    return offline


def _arquivo_consulta():
    base = Path(getattr(settings, 'DATA_DIR', Path(settings.BASE_DIR) / 'var'))
    base.mkdir(parents=True, exist_ok=True)
    return base / 'falabr-consulta.json'


def _base_guardada():
    """Parâmetros da consulta (tipo de formulário e ouvidoria) aprendidos numa vez anterior."""
    try:
        dados = json.loads(_arquivo_consulta().read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    if not isinstance(dados, dict) or not str(dados.get('ouvidoriaDestino') or '').isdigit():
        return None
    return {'tipoFormulario': str(dados.get('tipoFormulario') or '3'), 'ouvidoriaDestino': str(dados['ouvidoriaDestino'])}


def _guardar_base(base):
    if not base or not str(base.get('ouvidoriaDestino') or '').isdigit():
        return
    try:
        _arquivo_consulta().write_text(json.dumps(base), encoding='utf-8')
    except OSError:
        log.warning('Não foi possível guardar os parâmetros da consulta.', exc_info=True)


def _ha_aba_do_falabr():
    try:
        with urllib.request.urlopen(_endereco_cdp() + '/json', timeout=2) as resposta:
            abas = json.loads(resposta.read().decode('utf-8'))
    except Exception:
        return False
    return any(('falabr.cgu.gov.br' in a.get('url', '') or 'acesso.gov.br' in a.get('url', ''))
               for a in abas if a.get('type') == 'page')


def _abrir_aba_de_entrada():
    try:
        pedido = urllib.request.Request(_endereco_cdp() + '/json/new?' + ENTRADA, method='PUT')
        urllib.request.urlopen(pedido, timeout=3).close()
    except Exception:
        log.warning('Não foi possível abrir uma aba nova no Fala.BR.', exc_info=True)


def abrir():
    _cache_sessao['valor'] = None
    if _porta_responde():
        if not _ha_aba_do_falabr():
            _abrir_aba_de_entrada()
        _definir(
            fase='aguardando',
            mensagem='A janela do Fala.BR já está aberta. Entre com o gov.br nela.',
        )
        return
    executavel = _executavel()
    if not executavel:
        raise NavegadorError('Não encontrei o Edge nem o Chrome neste computador.')
    _encerrar_perfil()
    time.sleep(0.8)
    pasta = _perfil()
    subprocess.Popen(
        [
            executavel,
            f'--user-data-dir={pasta}',
            f'--remote-debugging-port={PORTA}',
            '--remote-allow-origins=*',
            '--no-first-run',
            '--no-default-browser-check',
            ENTRADA,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _esperar_porta()
    _definir(
        fase='aguardando',
        mensagem='A janela do Fala.BR está aberta. Entre com o gov.br nela.',
    )


def trazer():
    """Lê do Fala.BR tudo o que o órgão tem, sem depender do filtro da tela.

    A partir da lista "Tratar manifestações" que a pessoa abriu, o módulo
    descobre o tipo de formulário e a ouvidoria e faz duas consultas próprias
    numa aba temporária: as abertas (situações 1 a 5) e as encerradas (6 a 8),
    sem filtro de prazo. A aba da pessoa não é mexida.

    Devolve {'grupos': {'abertas': {...}, 'encerradas': {...}}}, cada grupo com
    'linhas', 'total' (número que o Fala.BR informa ou None) e 'completa'.
    """
    if not _porta_responde():
        raise NavegadorError('Clique em Logar e entre no gov.br antes de trazer os NUPs.')
    if not sessao(forcar=True)['online']:
        raise NavegadorError('Você ainda não está online no Fala.BR. Clique em Logar e entre com o gov.br.')
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise NavegadorError('O navegador automático não está instalado nesta demonstração.') from exc
    grupos = {}
    try:
        with sync_playwright() as playwright:
            navegador = playwright.chromium.connect_over_cdp(_endereco_cdp())
            contexto, base = _achar_consulta(navegador)
            guardada = _base_guardada()
            if base is not None and not base.get('ouvidoriaDestino') and guardada:
                base['ouvidoriaDestino'] = guardada['ouvidoriaDestino']
            if base is None and guardada and navegador.contexts:
                contexto, base = navegador.contexts[0], guardada
            if contexto is None or not base.get('ouvidoriaDestino'):
                raise NavegadorError(
                    'Só na primeira vez: na janela do Fala.BR, abra Tratar manifestações e deixe a lista na tela. '
                    'Depois clique em Trazer NUPs. O sistema guarda o órgão e não pede isso de novo.')
            _guardar_base(base)
            nova = contexto.new_page()
            try:
                for nome, situacoes in GRUPOS:
                    grupos[nome] = _consultar(nova, base, situacoes)
            finally:
                try:
                    nova.close()
                except Exception:
                    log.warning('Não foi possível fechar a aba temporária do Fala.BR.', exc_info=True)
    except NavegadorError:
        raise
    except Exception as exc:
        log.warning('Falha ao ler a janela do Fala.BR: %s', exc)
        raise NavegadorError('Não foi possível ler a janela do Fala.BR. Deixe a janela aberta e tente de novo.') from exc
    if not any(g['linhas'] for g in grupos.values()):
        raise NavegadorError(
            'O Fala.BR não devolveu manifestações. Confira se o login continua ativo e tente Trazer NUPs de novo.')
    _definir(fase='pronto', mensagem='')
    return {'grupos': grupos}


def _achar_consulta(navegador):
    """Acha a aba "Tratar manifestações" e devolve (contexto, parâmetros fixos)."""
    for contexto in navegador.contexts:
        for pagina in contexto.pages:
            try:
                partes = urlparse(pagina.url)
            except Exception:
                continue
            if 'falabr.cgu.gov.br' not in partes.netloc or 'manifestacao/tratar' not in partes.path:
                continue
            consulta = parse_qs(partes.query)
            base = {'tipoFormulario': (consulta.get('tipoFormulario') or ['3'])[0]}
            if consulta.get('ouvidoriaDestino'):
                base['ouvidoriaDestino'] = consulta['ouvidoriaDestino'][0]
            return contexto, base
    return None, None


def _consultar(pagina, base, situacoes):
    parametros = dict(base, situacoes=situacoes)
    pagina.goto(URL_LISTA + '?' + urlencode(parametros, safe=','), wait_until='domcontentloaded', timeout=45000)
    if not _aguardar_resultado(pagina):
        raise NavegadorError('O Fala.BR demorou para devolver a lista. Confira se o login continua ativo e tente de novo.')
    lido = _ler_paginas(pagina, voltar=False) or {'linhas': [], 'total': None}
    total = lido['total']
    lido['completa'] = total is None or len(lido['linhas']) >= total
    return lido


def _aguardar_resultado(pagina):
    """Espera a tabela ter linhas. "Total de registros: 0" só vale depois de alguns segundos."""
    inicio = time.time()
    while time.time() - inicio < 30:
        try:
            estado_tela = pagina.evaluate(_ESTADO_JS)
        except Exception:
            estado_tela = None
        if estado_tela:
            if estado_tela['linhas'] > 0:
                return True
            if estado_tela['total'] == 0 and time.time() - inicio > 6:
                return True
        time.sleep(0.4)
    return False


def fechar():
    _encerrar_perfil()
    _cache_sessao['valor'] = None
    _definir(fase='fechado', mensagem='Acesso encerrado nesta demonstração.')


def _definir(**valores):
    _estado.update(valores)


def _chave_coluna(texto):
    sem_acento = ''.join(
        c for c in unicodedata.normalize('NFD', texto or '') if unicodedata.category(c) != 'Mn')
    return re.sub(r'[^a-z]', '', sem_acento.lower())


def _linhas_da_tabela(dados):
    """Converte a tabela lida da tela em linhas, só com as colunas usadas."""
    indices = {}
    for posicao, titulo in enumerate(dados.get('cab') or []):
        campo = _COLUNAS.get(_chave_coluna(titulo))
        if campo and campo not in indices:
            indices[campo] = posicao
    if 'nup' not in indices or 'prazo' not in indices:
        return []
    saida = []
    for celulas in dados.get('linhas') or []:
        def texto(campo):
            posicao = indices.get(campo)
            if posicao is None or posicao >= len(celulas):
                return ''
            return celulas[posicao].get('texto') or ''
        achado = _NUP.search(texto('nup'))
        if not achado:
            continue
        registro = {campo: texto(campo) for campo in indices if campo != 'nup'}
        registro['nup'] = achado.group(0)
        registro['nup_normalizada'] = re.sub(r'\D', '', achado.group(0))
        registro['link'] = celulas[indices['nup']].get('href') or ''
        saida.append(registro)
    return saida


def _ler_paginas(pagina, voltar=True):
    dados = pagina.evaluate(_LER_JS)
    if not dados:
        return None
    linhas = _linhas_da_tabela(dados)
    total = dados.get('total')
    passos = 0
    while passos < MAX_PAGINAS:
        botao = pagina.query_selector(_PROXIMA)
        if botao is None or botao.is_disabled():
            break
        marca = pagina.evaluate(_PRIMEIRA_JS)
        botao.click()
        passos += 1
        if not _esperar_troca(pagina, marca):
            break
        linhas.extend(_linhas_da_tabela(pagina.evaluate(_LER_JS) or {}))
    # Devolve a lista para a primeira página, como a pessoa deixou.
    for _ in range(passos if voltar else 0):
        botao = pagina.query_selector(_ANTERIOR)
        if botao is None or botao.is_disabled():
            break
        marca = pagina.evaluate(_PRIMEIRA_JS)
        botao.click()
        _esperar_troca(pagina, marca)
    vistos = set()
    unicas = []
    for linha in linhas:
        if linha['nup_normalizada'] in vistos:
            continue
        vistos.add(linha['nup_normalizada'])
        unicas.append(linha)
    return {'linhas': unicas, 'total': total}


def _esperar_troca(pagina, marca):
    try:
        pagina.wait_for_function(_TROCOU_JS, arg=marca, timeout=10000)
        return True
    except Exception:
        log.warning('A página do Fala.BR não mudou a tempo.')
        return False


def _endereco_cdp():
    return f'http://127.0.0.1:{PORTA}'


def _perfil():
    base = Path(getattr(settings, 'DATA_DIR', Path(settings.BASE_DIR) / 'var'))
    pasta = base / 'falabr-perfil'
    pasta.mkdir(parents=True, exist_ok=True)
    return str(pasta)


def _executavel():
    programas_x86 = os.environ.get('PROGRAMFILES(X86)', r'C:\Program Files (x86)')
    programas = os.environ.get('PROGRAMFILES', r'C:\Program Files')
    local = os.environ.get('LOCALAPPDATA', '')
    candidatos = [
        Path(programas_x86) / 'Microsoft' / 'Edge' / 'Application' / 'msedge.exe',
        Path(programas) / 'Microsoft' / 'Edge' / 'Application' / 'msedge.exe',
        Path(local) / 'Google' / 'Chrome' / 'Application' / 'chrome.exe',
        Path(programas) / 'Google' / 'Chrome' / 'Application' / 'chrome.exe',
    ]
    for caminho in candidatos:
        if caminho.is_file():
            return str(caminho)
    return None


def _porta_responde():
    try:
        with urllib.request.urlopen(_endereco_cdp() + '/json/version', timeout=1) as resposta:
            return resposta.status == 200
    except Exception:
        return False


def _esperar_porta():
    limite = time.time() + 20
    while time.time() < limite:
        if _porta_responde():
            return
        time.sleep(0.3)
    raise NavegadorError('A janela do Fala.BR demorou para abrir. Feche qualquer janela antiga do Fala.BR e clique em Logar de novo.')


def _encerrar_perfil():
    """Fecha só a janela desta demonstração, não o Edge ou o Chrome do dia a dia."""
    comando = (
        "Get-CimInstance Win32_Process | "
        "Where-Object { $_.CommandLine -like '*falabr-perfil*' } | "
        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
    )
    try:
        subprocess.run(
            ['powershell', '-NoProfile', '-Command', comando],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=25,
            check=False,
        )
    except Exception:
        log.warning('Não foi possível fechar a janela anterior do Fala.BR.', exc_info=True)
