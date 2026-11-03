"""Automação que baixa, no Fala.BR, o PDF e os anexos dos pedidos escolhidos.

Usa a mesma janela comum do Edge/Chrome em que a pessoa entrou no gov.br
(ver navegador_falabr). Para cada NUP abre o pedido numa aba temporária,
clica em "Exportar" e, se houver anexos, em "Baixar todos". Nada é alterado
no Fala.BR: só leitura e download. Os botões Analisar, Encaminhar e Reclamar
não são tocados aqui.

Cada pedido vira uma pasta no padrão do controle (ver pastas_pedidos) dentro de
settings.LAI_PASTA_ANO, e ganha uma linha na planilha de controle (ver planilha_controle).
"""
import io
import logging
import re
import shutil
import tempfile
import threading
import time
import zipfile
from pathlib import Path

from django.conf import settings
from django.db import connection
from django.utils import timezone

from . import navegador_falabr, pastas_pedidos, planilha_controle
from .navegador_falabr import NavegadorError

log = logging.getLogger(__name__)

PREFIXO_LINK = 'https://falabr.cgu.gov.br/'
MODAL = '#modalConfirmacaoDadosManifestante'
# "Incluir dados do manifestante na impressão?" Fica desmarcado: o PDF sai sem nome e contatos do cidadão.
INCLUIR_DADOS_MANIFESTANTE = False
_trava = threading.Lock()
_estado = {}

# Quantos anexos a tabela do pedido mostra (0 quando não há nenhum).
_ANEXOS_JS = """() => {
    const t = document.querySelector('#idAnexosTable') || document.querySelector('[id^=idAnexosTable]');
    const caixa = t ? (t.closest('section, .br-table, div') || t) : null;
    const m = caixa ? (caixa.innerText.match(/Total de registros:\\s*(\\d+)/) || [])[1] : null;
    const linhas = t ? Array.from(t.querySelectorAll('tbody tr')).filter(tr => tr.querySelectorAll('td').length > 1).length : 0;
    const botao = document.querySelector('#idBaixarTodosAnexos');
    return {total: m ? parseInt(m, 10) : null, linhas: linhas,
            botao: !!botao && !botao.disabled && !!(botao.offsetWidth || botao.offsetHeight)};
}"""


def pasta_base():
    return Path(settings.LAI_PASTA_ANO)


def estado():
    with _trava:
        copia = dict(_estado)
        copia['resultados'] = [dict(r) for r in _estado.get('resultados', [])]
    return copia


def iniciar(itens):
    """Começa em segundo plano. `itens` = [{'nup','link','tema','cadastro','prazo','pk'}].

    Os pedidos são processados na ordem do NUP, que é a ordem da sequência das pastas.
    """
    itens = [i for i in itens if str(i.get('link') or '').startswith(PREFIXO_LINK)]
    if not itens:
        raise NavegadorError('Nenhum dos pedidos marcados tem link do Fala.BR. Traga os NUPs de novo e tente outra vez.')
    if not navegador_falabr._porta_responde():
        raise NavegadorError('A janela do Fala.BR não está aberta. Clique em Logar e entre no gov.br antes.')
    if not navegador_falabr.sessao(forcar=True)['online']:
        raise NavegadorError('Você não está online no Fala.BR. Clique em Logar e entre no gov.br antes.')
    itens = sorted(itens, key=lambda i: pastas_pedidos.so_digitos(i['nup']))
    with _trava:
        if _estado.get('rodando'):
            raise NavegadorError('A automação já está rodando. Aguarde o fim.')
        _estado.clear()
        _estado.update(
            rodando=True, total=len(itens), atual=0, nup='', etapa='Iniciando automatização…',
            resultados=[], pasta=str(pasta_base()), planilha='', planilha_erro='',
            planilha_ativa=bool(getattr(settings, 'LAI_PLANILHA_ATIVA', False)),
            inicio=time.time(), fim=None, erro='')
    threading.Thread(target=_executar, args=(itens,), daemon=True).start()


def _definir(**valores):
    with _trava:
        _estado.update(valores)


def _executar(itens):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        _definir(rodando=False, erro='O navegador automático não está instalado.', fim=time.time())
        return
    prontos = []
    marcados = []
    try:
        base = pasta_base()
        sequencia = pastas_pedidos.proxima_sequencia(base)
        with sync_playwright() as playwright:
            navegador = playwright.chromium.connect_over_cdp(navegador_falabr._endereco_cdp())
            contexto = navegador.contexts[0]
            for posicao, item in enumerate(itens, start=1):
                _definir(atual=posicao, nup=item['nup'], etapa='Conferindo a pasta')
                resultado = {'nup': item['nup'], 'pasta': '', 'pdf': False, 'anexos': 0,
                             'ja_baixado': False, 'planilha': '', 'erro': ''}
                aba = None
                try:
                    existente = pastas_pedidos.achar_pasta(base, item['nup'])
                    if existente is not None and _ja_tem_pdf(existente, item['nup']):
                        # Já baixado antes: não baixa de novo. Só ajusta o nome se o tema foi editado.
                        pasta = existente
                        if item.get('tema') and item.get('tema_manual'):
                            pasta, _, _ = pastas_pedidos.preparar_pasta(base, item['nup'], item['tema'], sequencia)
                        resultado['ja_baixado'] = resultado['pdf'] = True
                        if not item.get('tema'):
                            item['tema'] = _tema_do_nome(pasta.name, item['nup'])
                    else:
                        _definir(etapa='Abrindo o pedido')
                        aba = contexto.new_page()
                        with tempfile.TemporaryDirectory() as temporaria:
                            pdf_temp = _exportar_pdf(aba, item, Path(temporaria), resultado)
                            if pdf_temp is not None:
                                if not item.get('tema'):
                                    item['tema'] = _tema_do_pdf(pdf_temp)
                                pasta, criada, _ = pastas_pedidos.preparar_pasta(
                                    base, item['nup'], item.get('tema'), sequencia)
                                if criada:
                                    sequencia += 1
                                destino_pdf = pasta / pastas_pedidos.nome_do_pdf(item['nup'])
                                shutil.move(str(pdf_temp), str(destino_pdf))
                                resultado['pdf'] = True
                                try:
                                    _baixar_anexos(aba, item, pasta, resultado)
                                except Exception as exc:
                                    # Sem o PDF na pasta o pedido é tentado inteiro na próxima vez.
                                    log.warning('Anexos de %s não baixaram: %s', item['nup'], exc, exc_info=True)
                                    destino_pdf.unlink(missing_ok=True)
                                    resultado['pdf'] = False
                                    resultado['erro'] = 'Os anexos não baixaram: ' + _resumo_erro(exc)
                    if resultado['pdf']:
                        resultado['pasta'] = pasta.name
                        prontos.append(item)
                        marcados.append((item, pasta.name))
                except Exception as exc:
                    log.warning('Falha ao baixar %s: %s', item['nup'], exc, exc_info=True)
                    resultado['erro'] = _resumo_erro(exc)
                finally:
                    if aba is not None:
                        try:
                            aba.close()
                        except Exception:
                            pass
                with _trava:
                    _estado['resultados'].append(resultado)
    except Exception as exc:
        log.warning('Falha na automação do Fala.BR: %s', exc, exc_info=True)
        _definir(erro='Não foi possível controlar a janela do Fala.BR. Deixe-a aberta e tente de novo.')
    try:
        # O banco só é usado fora do bloco do Playwright, que roda um laço assíncrono nesta linha de execução.
        for item, nome in marcados:
            _marcar_baixado(item, nome)
        if prontos and getattr(settings, 'LAI_PLANILHA_ATIVA', False):
            _definir(etapa='Preenchendo a planilha de controle')
            _preencher_planilha(prontos)
    finally:
        _definir(rodando=False, etapa='Concluído', fim=time.time())
        connection.close()


def _preencher_planilha(itens):
    try:
        linhas, arquivo = planilha_controle.adicionar(itens)
    except planilha_controle.PlanilhaErro as exc:
        _definir(planilha_erro=str(exc))
        return
    except Exception as exc:
        log.warning('Falha ao preencher a planilha: %s', exc, exc_info=True)
        _definir(planilha_erro='Não foi possível preencher a planilha.')
        return
    with _trava:
        _estado['planilha'] = str(arquivo)
        for resultado in _estado['resultados']:
            achado = linhas.get(resultado['nup'])
            if achado:
                if achado['nova']:
                    resultado['planilha'] = f'linha {achado["linha"]}'
                else:
                    resultado['planilha'] = (f'já estava na linha {achado["linha"]}'
                                             + (' (objeto atualizado)' if achado.get('objeto_atualizado') else ''))


def _marcar_baixado(item, pasta_nome):
    if not item.get('pk'):
        return
    try:
        from .models import ManifestacaoFalabr
        ManifestacaoFalabr.objects.filter(pk=item['pk']).update(
            pasta=pasta_nome[:300], baixado_em=timezone.now())
    except Exception:
        log.warning('Não foi possível marcar %s como baixado.', item['nup'], exc_info=True)


def _resumo_erro(exc):
    texto = str(exc).splitlines()[0] if str(exc) else exc.__class__.__name__
    return texto[:160]


def _ja_tem_pdf(pasta, nup):
    return (Path(pasta) / pastas_pedidos.nome_do_pdf(nup)).is_file()


def _tema_do_pdf(caminho):
    """Sugere o tema a partir do resumo que o extrator lê no PDF. Vazio se não der."""
    try:
        from .extracao import extrair
        dados = extrair(io.BytesIO(Path(caminho).read_bytes()))
        # O campo Resumo do Fala.BR costuma vir vazio ("-"); nesse caso vale o texto do pedido.
        sem_resumo = any('Resumo ausente' in aviso for aviso in dados.get('avisos', []))
        return pastas_pedidos.sugerir_tema(dados.get('teor') if sem_resumo else dados.get('resumo'))
    except Exception:
        log.warning('Não foi possível sugerir o tema a partir do PDF.', exc_info=True)
        return ''


def _tema_do_nome(nome, nup):
    return nome.split(f' - {nup} - ', 1)[-1] if f' - {nup} - ' in nome else ''


def _exportar_pdf(aba, item, pasta, resultado):
    """Abre o pedido, exporta o PDF para `pasta` e devolve o caminho (ou None, com o erro em `resultado`)."""
    pasta = Path(pasta)
    aba.goto(item['link'], wait_until='domcontentloaded', timeout=45000)
    aba.wait_for_selector('#btnExportar', state='visible', timeout=30000)
    time.sleep(1.5)  # a tabela de anexos carrega depois dos botões

    _definir(etapa='Exportando o PDF')
    aba.click('#btnExportar')
    # O Fala.BR pergunta se deve incluir os dados do manifestante. Padrão: não incluir.
    aba.wait_for_selector(MODAL + '-button-primary', state='visible', timeout=20000)
    caixa = aba.locator('#chkExibeDadosManifestante')
    if caixa.count():
        if INCLUIR_DADOS_MANIFESTANTE and not caixa.is_checked():
            caixa.check(force=True)
        elif not INCLUIR_DADOS_MANIFESTANTE and caixa.is_checked():
            caixa.uncheck(force=True)
    with aba.expect_download(timeout=90000) as baixando:
        aba.click(MODAL + '-button-primary')
    destino = pasta / pastas_pedidos.nome_do_pdf(item['nup'])
    baixando.value.save_as(str(destino))
    if destino.stat().st_size < 200 or destino.read_bytes()[:4] != b'%PDF':
        destino.unlink(missing_ok=True)
        resultado['erro'] = 'O Exportar não devolveu um PDF.'
        return None
    return destino


def _baixar_anexos(aba, item, pasta, resultado):
    anexos = aba.evaluate(_ANEXOS_JS)
    tem = (anexos.get('total') or anexos.get('linhas') or 0) > 0 and anexos.get('botao')
    if tem:
        _definir(etapa='Baixando os anexos')
        with aba.expect_download(timeout=120000) as baixando:
            aba.click('#idBaixarTodosAnexos')
        resultado['anexos'] = _guardar_anexos(baixando.value, pasta, item['nup'])


def _nome_seguro(nome):
    nome = Path(str(nome).replace('\\', '/')).name
    return re.sub(r'[<>:"|?*\x00-\x1f]', '_', nome).strip('. ') or 'anexo'


def _guardar_anexos(download, pasta, nup):
    """Salva o que "Baixar todos" devolveu, direto na pasta do pedido.

    Se vier um ZIP, abre os arquivos com nomes seguros. O nome padrão do Fala.BR
    (`<NUP sem pontos>_pdf_1.pdf`) passa a usar o NUP com pontos.
    """
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    nome = _nome_seguro(download.suggested_filename or 'anexos')
    temporario = pasta / ('_baixado_' + nome)
    download.save_as(str(temporario))
    try:
        if zipfile.is_zipfile(temporario):
            quantidade = 0
            with zipfile.ZipFile(temporario) as pacote:
                for info in pacote.infolist():
                    if info.is_dir():
                        continue
                    final = pastas_pedidos.nome_do_anexo(_nome_seguro(info.filename), nup)
                    destino = _destino_livre(pasta, final)
                    with pacote.open(info) as origem, open(destino, 'wb') as saida:
                        saida.write(origem.read())
                    quantidade += 1
            return quantidade
        destino = _destino_livre(pasta, pastas_pedidos.nome_do_anexo(nome, nup))
        temporario.replace(destino)
        return 1
    finally:
        if temporario.exists():
            temporario.unlink()


def _destino_livre(pasta, nome):
    destino = pasta / nome
    contador = 2
    while destino.exists():
        destino = pasta / f'{Path(nome).stem} ({contador}){Path(nome).suffix}'
        contador += 1
    return destino
