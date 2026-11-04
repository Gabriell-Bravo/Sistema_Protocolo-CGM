"""Ponte com a extensão do navegador (Edge/Chrome) que lê o Fala.BR.

O sistema roda no servidor e não consegue entrar no gov.br. Quem entra é a pessoa, no navegador
dela. A extensão, instalada nesse navegador, lê o que o Fala.BR mostra (lista de pedidos, PDF e
anexos) e entrega aqui. Este módulo recebe o que a extensão manda, monta as pastas dos pedidos e
guarda o andamento da tarefa para a tela acompanhar.

O andamento fica num arquivo (e não na memória) porque o servidor roda vários processos.
"""
import contextlib
import hashlib
import io
import json
import logging
import os
import re
import tempfile
import threading
import time
import uuid
import zipfile
from datetime import date
from pathlib import Path

from django.conf import settings
from django.core import signing

from . import acompanhamento, navegador_falabr, pastas_pedidos, planilha_controle
from .automacao_falabr import (PREFIXO_LINK, _destino_livre, _ja_tem_pdf, _marcar_baixado, _nome_seguro,
                               _tema_do_nome, _tema_do_pdf, pasta_base)

log = logging.getLogger(__name__)

VERSAO = '1.0.0'
_SAL = 'lai-extensao'
VALIDADE_TOKEN = 365 * 24 * 3600
SEM_SINAL = {'trazer': 75, 'pastas': 75}   # segundos sem notícia da extensão até dar a tarefa por parada (ela avisa a cada 10 s)
LIMITE_PEDIDO = 400 * 1024 * 1024            # tamanho máximo de um pedido (PDF + anexos já descompactados)
PASTA_EXTENSAO = Path(__file__).resolve().parent / 'extensao_navegador'
ARQUIVOS_EXTENSAO = ('background.js', 'ponte.js', 'popup.html', 'popup.js')
_trava = threading.Lock()


class ExtensaoError(Exception):
    pass


# ------------------------------------------------------------------ token da extensão

def _impressao(usuario):
    return hashlib.sha256((usuario.password or '').encode()).hexdigest()[:16]


def gerar_token(usuario):
    """Código que a extensão usa para falar com o sistema. Muda se a senha do usuário mudar."""
    return signing.dumps({'u': usuario.pk, 'f': _impressao(usuario)}, salt=_SAL)


def usuario_do_token(token):
    """Usuário dono do código, ou None se o código é inválido, velho ou de senha trocada."""
    from django.contrib.auth import get_user_model
    try:
        dados = signing.loads(token or '', salt=_SAL, max_age=VALIDADE_TOKEN)
        usuario = get_user_model().objects.get(pk=dados['u'])
    except (signing.BadSignature, KeyError, TypeError, get_user_model().DoesNotExist):
        return None
    if not usuario.is_active or dados.get('f') != _impressao(usuario):
        return None
    return usuario


# ------------------------------------------------------------------ pacote da extensão

def montar_pacote(origem, usuario):
    """ZIP da extensão já apontando para este sistema (`origem` = 'https://servidor') e com o código do usuário."""
    origem = origem.rstrip('/')
    manifesto = {
        'manifest_version': 3,
        'name': 'LAI CGM - ponte com o Fala.BR',
        'version': VERSAO,
        'description': 'Lê o Fala.BR no seu navegador e entrega ao sistema da CGM os NUPs, PDFs e anexos.',
        'permissions': ['tabs', 'scripting', 'downloads'],
        'host_permissions': ['https://falabr.cgu.gov.br/*', origem + '/*'],
        'background': {'service_worker': 'background.js'},
        'content_scripts': [{'matches': [origem + '/lai/*'], 'js': ['ponte.js'], 'run_at': 'document_idle'}],
        'action': {'default_popup': 'popup.html', 'default_title': 'LAI CGM'},
    }
    configuracao = 'self.LAI_CONFIG = ' + json.dumps(
        {'servidor': origem, 'token': gerar_token(usuario), 'versao': VERSAO}, ensure_ascii=False) + ';\n'
    leia_me = (
        'Extensão LAI CGM\r\n\r\n'
        '1. Extraia esta pasta num lugar fixo (por exemplo C:\\LAI-extensao). Não apague depois.\r\n'
        '2. No Edge abra edge://extensions (no Chrome, chrome://extensions) e ligue o Modo de desenvolvedor.\r\n'
        '3. Clique em "Carregar sem pacote" e escolha esta pasta.\r\n'
        '4. Abra o Fala.BR, entre com o gov.br e use a aba LAI do sistema.\r\n\r\n'
        'Este arquivo traz o código de acesso de quem o baixou. Não envie a outras pessoas.\r\n')
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, 'w', zipfile.ZIP_DEFLATED) as pacote:
        pacote.writestr('manifest.json', json.dumps(manifesto, ensure_ascii=False, indent=2))
        pacote.writestr('config.js', configuracao)
        pacote.writestr('LEIA-ME.txt', leia_me)
        for nome in ARQUIVOS_EXTENSAO:
            pacote.write(PASTA_EXTENSAO / nome, nome)
    return saida.getvalue()


# ------------------------------------------------------------------ andamento da tarefa

def _arquivo():
    base = Path(getattr(settings, 'DATA_DIR', Path(settings.BASE_DIR) / 'var'))
    base.mkdir(parents=True, exist_ok=True)
    return base / 'tarefa-extensao.json'


def _ler():
    try:
        dados = json.loads(_arquivo().read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    return dados if isinstance(dados, dict) else {}


def _gravar(dados):
    alvo = _arquivo()
    temporario = alvo.with_name(alvo.name + f'.{os.getpid()}.tmp')
    temporario.write_text(json.dumps(dados, ensure_ascii=False), encoding='utf-8')
    os.replace(temporario, alvo)


@contextlib.contextmanager
def _bloqueio():
    """Um de cada vez, mesmo entre os processos do servidor (a extensão manda sinais e arquivos ao mesmo tempo)."""
    with _trava:
        trava = _arquivo().with_suffix('.lock')
        limite = time.time() + 20
        while True:
            try:
                os.close(os.open(str(trava), os.O_CREAT | os.O_EXCL | os.O_WRONLY))
                break
            except FileExistsError:
                try:
                    if time.time() - trava.stat().st_mtime > 30:
                        trava.unlink(missing_ok=True)
                        continue
                except OSError:
                    pass
                if time.time() > limite:
                    raise ExtensaoError('O andamento da tarefa está ocupado. Tente de novo.')
                time.sleep(0.05)
        try:
            yield
        finally:
            trava.unlink(missing_ok=True)


def _atualizar(**campos):
    with _bloqueio():
        dados = _ler()
        dados.update(campos)
        dados['atualizado'] = time.time()
        _gravar(dados)
        return dados


def estado():
    """Andamento para a tela. Tarefa sem sinal da extensão por muito tempo conta como parada."""
    dados = _ler()
    if not dados:
        return {'tipo': '', 'rodando': False, 'etapa': '', 'resultados': [], 'erro': ''}
    if dados.get('rodando') and time.time() - dados.get('atualizado', 0) > SEM_SINAL.get(dados.get('tipo'), 240):
        dados = _atualizar(rodando=False, fim=time.time(), etapa='Parou',
                           erro='A extensão parou de responder. Confira se o navegador está aberto e tente de novo.')
    publico = {k: v for k, v in dados.items() if k != 'itens'}
    publico['resultados'] = [dict(r) for r in dados.get('resultados', [])]
    return publico


def _exigir_livre():
    if estado().get('rodando'):
        raise ExtensaoError('Já há uma tarefa em andamento. Aguarde o fim.')


def cancelar(motivo='Cancelado.'):
    if _ler().get('rodando'):
        _atualizar(rodando=False, fim=time.time(), etapa='Parou', erro=motivo)


def progresso(campos):
    """Sinal de vida e andamento vindos da extensão. Devolve False se a tarefa já foi encerrada."""
    dados = _ler()
    if not dados.get('rodando'):
        return False
    novos = {}
    if campos.get('etapa'):
        novos['etapa'] = str(campos['etapa'])[:200]
    if campos.get('nup'):
        novos['nup'] = str(campos['nup'])[:40]
    if str(campos.get('atual') or '').isdigit():
        novos['atual'] = int(campos['atual'])
    if campos.get('erro'):
        novos.update(rodando=False, fim=time.time(), etapa='Parou', erro=str(campos['erro'])[:600])
    _atualizar(**novos)
    return not campos.get('erro')


# ------------------------------------------------------------------ trazer NUPs

def iniciar_trazer():
    _exigir_livre()
    _gravar({'id': uuid.uuid4().hex, 'tipo': 'trazer', 'rodando': True, 'etapa': 'Aguardando a extensão…',
             'inicio': time.time(), 'fim': None, 'erro': '', 'resumo': '', 'resultados': [],
             'atualizado': time.time()})
    return {'base': navegador_falabr._base_guardada()}


def _unicas(tabela):
    vistos, saida = set(), []
    for linha in navegador_falabr._linhas_da_tabela(tabela if isinstance(tabela, dict) else {}):
        if linha['nup_normalizada'] in vistos:
            continue
        vistos.add(linha['nup_normalizada'])
        saida.append(linha)
    return saida


def receber_leitura(dados):
    """Grava a lista que a extensão leu. `dados` = {'base', 'grupos': {'abertas': {cab, linhas, total}, ...}}."""
    grupos = {}
    for nome in ('abertas', 'encerradas'):
        bruto = (dados.get('grupos') or {}).get(nome) or {}
        linhas = _unicas(bruto)
        total = bruto.get('total') if isinstance(bruto.get('total'), int) else None
        grupos[nome] = {'linhas': linhas, 'total': total, 'completa': total is None or len(linhas) >= total}
    if not any(g['linhas'] for g in grupos.values()):
        raise ExtensaoError(
            'O Fala.BR não devolveu manifestações. Confira se o login continua ativo e clique em Trazer NUPs de novo.')
    navegador_falabr._guardar_base(dados.get('base') if isinstance(dados.get('base'), dict) else None)
    gravado = acompanhamento.sincronizar_leitura({'grupos': grupos})
    aviso = resumo_da_leitura(gravado)
    _atualizar(rodando=False, fim=time.time(), etapa='Concluído', resumo=aviso, erro='')
    return aviso


def resumo_da_leitura(gravado):
    aviso = (f'{gravado["abertas"]} aberta(s) e {gravado["encerradas"]} encerrada(s) lida(s) do Fala.BR: '
             f'{gravado["novas"]} nova(s) e {gravado["alteradas"]} com prazo ou situação alterados.')
    if gravado['saiu']:
        aviso += f' {gravado["saiu"]} saiu(ram) da fila aberta desde a última leitura.'
    if gravado['incompleta']:
        aviso += ' O Fala.BR informou mais registros do que foram lidos; leia de novo para completar.'
    return aviso


# ------------------------------------------------------------------ automatizar pastas

def _texto_data(valor):
    return valor.isoformat() if isinstance(valor, date) else (str(valor) if valor else '')


def iniciar_pastas(itens):
    """Prepara a tarefa. `itens` = [{'nup','link','tema','tema_manual','cadastro','prazo','pk'}].

    Quem já tem pasta com PDF é resolvido aqui. Devolve os que a extensão ainda precisa baixar.
    """
    itens = [i for i in itens if str(i.get('link') or '').startswith(PREFIXO_LINK)]
    if not itens:
        raise ExtensaoError('Nenhum dos pedidos marcados tem link do Fala.BR. Traga os NUPs de novo e tente outra vez.')
    _exigir_livre()
    itens = sorted(itens, key=lambda i: pastas_pedidos.so_digitos(i['nup']))
    base = pasta_base()
    resultados, pendentes, marcados = [], [], []
    for item in itens:
        existente = pastas_pedidos.achar_pasta(base, item['nup'])
        if existente is None or not _ja_tem_pdf(existente, item['nup']):
            pendentes.append(item)
            continue
        # Já baixado antes: não baixa de novo. Só ajusta o nome se o tema foi editado.
        pasta = existente
        if item.get('tema') and item.get('tema_manual'):
            pasta, _, _ = pastas_pedidos.preparar_pasta(base, item['nup'], item['tema'], pastas_pedidos.proxima_sequencia(base))
        if not item.get('tema'):
            item['tema'] = _tema_do_nome(pasta.name, item['nup'])
        resultados.append({'nup': item['nup'], 'pasta': pasta.name, 'pdf': True, 'anexos': 0,
                           'ja_baixado': True, 'planilha': '', 'erro': ''})
        marcados.append((item, pasta.name))
    for item, nome in marcados:
        _marcar_baixado(item, nome)
    guardados = {}
    for item in itens:
        guardados[pastas_pedidos.so_digitos(item['nup'])] = {
            'pk': item.get('pk'), 'nup': item['nup'], 'link': item['link'], 'tema': item.get('tema') or '',
            'tema_manual': bool(item.get('tema_manual')), 'cadastro': _texto_data(item.get('cadastro')),
            'prazo': _texto_data(item.get('prazo'))}
    _gravar({'id': uuid.uuid4().hex, 'tipo': 'pastas', 'rodando': True, 'total': len(itens),
             'atual': len(resultados), 'nup': '', 'etapa': 'Aguardando a extensão…', 'resultados': resultados,
             'itens': guardados, 'pasta': str(base), 'planilha': '', 'planilha_erro': '',
             'planilha_ativa': bool(getattr(settings, 'LAI_PLANILHA_ATIVA', False)),
             'inicio': time.time(), 'fim': None, 'erro': '', 'atualizado': time.time()})
    if not pendentes:
        concluir()
    return {'total': len(itens), 'ja_prontos': len(resultados),
            'pendentes': [{'nup': i['nup'], 'link': i['link']} for i in pendentes]}


def _anexos_para_pasta(pasta, nup, anexos):
    """Guarda os anexos na pasta do pedido. ZIP é aberto, com nomes seguros. Devolve a quantidade."""
    quantidade = 0
    total = 0
    for nome, dados in anexos:
        if zipfile.is_zipfile(io.BytesIO(dados)):
            with zipfile.ZipFile(io.BytesIO(dados)) as pacote:
                for info in pacote.infolist():
                    if info.is_dir():
                        continue
                    total += info.file_size
                    if total > LIMITE_PEDIDO:
                        raise ExtensaoError('Os anexos descompactados passam do limite permitido.')
                    final = pastas_pedidos.nome_do_anexo(_nome_seguro(info.filename), nup)
                    with pacote.open(info) as origem, open(_destino_livre(pasta, final), 'wb') as saida:
                        saida.write(origem.read())
                    quantidade += 1
        else:
            total += len(dados)
            if total > LIMITE_PEDIDO:
                raise ExtensaoError('Os anexos passam do limite permitido.')
            nome = _nome_seguro(nome or 'anexo')
            if not Path(nome).suffix and dados[:4] == b'%PDF':
                nome += '.pdf'
            with open(_destino_livre(pasta, pastas_pedidos.nome_do_anexo(nome, nup)), 'wb') as saida:
                saida.write(dados)
            quantidade += 1
    return quantidade


def receber_pedido(nup, pdf, anexos):
    """Cria a pasta do pedido com o PDF e os anexos que a extensão baixou do Fala.BR."""
    dados = _ler()
    chave = pastas_pedidos.so_digitos(nup)
    item = (dados.get('itens') or {}).get(chave)
    if not dados.get('rodando') or dados.get('tipo') != 'pastas' or item is None:
        raise ExtensaoError('Este pedido não faz parte da tarefa em andamento.')
    if pdf[:4] != b'%PDF' or len(pdf) < 200:
        raise ExtensaoError('O arquivo enviado como PDF não é um PDF.')
    if len(pdf) + sum(len(d) for _, d in anexos) > LIMITE_PEDIDO:
        raise ExtensaoError('O pedido passa do tamanho máximo permitido.')
    base = pasta_base()
    nup_pontos = item['nup']
    tema = item.get('tema')
    if not tema:
        with tempfile.TemporaryDirectory() as temporaria:
            temporario = Path(temporaria) / 'pedido.pdf'
            temporario.write_bytes(pdf)
            tema = _tema_do_pdf(temporario)
    pasta, _, _ = pastas_pedidos.preparar_pasta(base, nup_pontos, tema, pastas_pedidos.proxima_sequencia(base))
    destino_pdf = pasta / pastas_pedidos.nome_do_pdf(nup_pontos)
    destino_pdf.write_bytes(pdf)
    try:
        quantidade = _anexos_para_pasta(pasta, nup_pontos, anexos)
    except Exception:
        # Sem o PDF na pasta o pedido é tentado inteiro na próxima vez.
        destino_pdf.unlink(missing_ok=True)
        raise
    item['tema'] = tema
    resultado = {'nup': nup_pontos, 'pasta': pasta.name, 'pdf': True, 'anexos': quantidade,
                 'ja_baixado': False, 'planilha': '', 'erro': ''}
    _marcar_baixado(item, pasta.name)
    _registrar(resultado, chave, item)
    return resultado


def registrar_falha(nup, erro):
    dados = _ler()
    chave = pastas_pedidos.so_digitos(nup)
    item = (dados.get('itens') or {}).get(chave)
    if not dados.get('rodando') or item is None:
        return
    _registrar({'nup': item['nup'], 'pasta': '', 'pdf': False, 'anexos': 0, 'ja_baixado': False,
                'planilha': '', 'erro': str(erro or 'Falha sem detalhes.')[:600]}, chave, None)


def _registrar(resultado, chave, item_atualizado):
    with _bloqueio():
        dados = _ler()
        if item_atualizado is not None:
            dados['itens'][chave] = item_atualizado
        dados['resultados'] = [r for r in dados.get('resultados', []) if r.get('nup') != resultado['nup']] + [resultado]
        dados['atual'] = len(dados['resultados'])
        dados['atualizado'] = time.time()
        _gravar(dados)


def _data_do_texto(valor):
    return acompanhamento.data_do_texto(valor)


def concluir():
    """Fim da tarefa de pastas: preenche a planilha (se ligada) e libera a tela."""
    dados = _ler()
    if dados.get('tipo') != 'pastas' or not dados.get('rodando'):
        return
    prontos = []
    for resultado in dados.get('resultados', []):
        if resultado.get('pdf') and not resultado.get('erro'):
            item = (dados.get('itens') or {}).get(pastas_pedidos.so_digitos(resultado['nup']))
            if item:
                prontos.append(dict(item, cadastro=_data_do_texto(item.get('cadastro')), prazo=_data_do_texto(item.get('prazo'))))
    campos = {}
    if prontos and getattr(settings, 'LAI_PLANILHA_ATIVA', False):
        _atualizar(etapa='Preenchendo a planilha de controle')
        try:
            linhas, arquivo = planilha_controle.adicionar(prontos)
            campos['planilha'] = str(arquivo)
            for resultado in dados.get('resultados', []):
                achado = linhas.get(resultado['nup'])
                if achado:
                    resultado['planilha'] = (f'linha {achado["linha"]}' if achado['nova'] else
                                             f'já estava na linha {achado["linha"]}'
                                             + (' (objeto atualizado)' if achado.get('objeto_atualizado') else ''))
            campos['resultados'] = dados['resultados']
        except planilha_controle.PlanilhaErro as exc:
            campos['planilha_erro'] = str(exc)
        except Exception as exc:
            log.warning('Falha ao preencher a planilha: %s', exc, exc_info=True)
            campos['planilha_erro'] = 'Não foi possível preencher a planilha.'
    _atualizar(rodando=False, etapa='Concluído', fim=time.time(), **campos)


# ------------------------------------------------------------------ baixar as pastas da tarefa

def pastas_da_tarefa():
    """Pastas dos pedidos prontos na última tarefa (para baixar tudo num ZIP)."""
    base = pasta_base()
    achadas = []
    for resultado in _ler().get('resultados', []):
        if resultado.get('pdf') and resultado.get('pasta'):
            pasta = base / resultado['pasta']
            if pasta.is_dir() and pasta.resolve().parent == base.resolve():
                achadas.append(pasta)
    return achadas


def zip_das_pastas():
    """Arquivo temporário com as pastas da tarefa. Quem chama apaga depois de enviar."""
    arquivo = tempfile.NamedTemporaryFile(prefix='lai-pastas-', suffix='.zip', delete=False)
    with zipfile.ZipFile(arquivo, 'w', zipfile.ZIP_DEFLATED) as pacote:
        for pasta in pastas_da_tarefa():
            for caminho in sorted(pasta.rglob('*')):
                if caminho.is_file():
                    pacote.write(caminho, str(Path(pasta.name) / caminho.relative_to(pasta)))
    arquivo.close()
    return arquivo.name
