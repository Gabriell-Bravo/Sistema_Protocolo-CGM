import io
import json
import tempfile
import time
import zipfile
from datetime import date
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings
from django.urls import reverse

from lai import ponte_extensao
from lai.models import ManifestacaoFalabr, Operador

NUP = '03996.2026.000936-10'
LINK = 'https://falabr.cgu.gov.br/web/manifestacao/detalhar/1'
PDF = b'%PDF-1.4\n' + b'conteudo ficticio do pedido ' * 20 + b'\n%%EOF'
CAB = ['Número', 'Órgão Destinatário', 'Assunto', 'Serviço', 'Tipo', 'E-mail do manifestante',
       'Cadastro', 'Prazo', 'Situação', 'Responsável']


def _zip(**arquivos):
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, 'w') as pacote:
        for nome, dados in arquivos.items():
            pacote.writestr(nome, dados)
    return saida.getvalue()


def _linha(nup, assunto='Quadro de cargos', prazo='03/11/2026', situacao='Cadastrada'):
    return [{'texto': nup, 'href': LINK}, {'texto': 'Prefeitura', 'href': ''}, {'texto': assunto, 'href': ''},
            {'texto': '', 'href': ''}, {'texto': 'Acesso à Informação', 'href': ''},
            {'texto': 'cidadao@example.invalid', 'href': ''}, {'texto': '29/09/2026', 'href': ''},
            {'texto': prazo, 'href': ''}, {'texto': situacao, 'href': ''}, {'texto': 'Fulana', 'href': ''}]


class _Base(TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._ajustes = override_settings(
            LAI_SOMENTE_ADMIN=False, DATA_DIR=Path(self._tmp.name), LAI_PASTA_ANO=Path(self._tmp.name) / 'pedidos' / '2026',
            LAI_PLANILHA_ATIVA=False)
        self._ajustes.enable()
        self.addCleanup(self._ajustes.disable)
        self.usuario = get_user_model().objects.create_user('operador', password='teste-lai-123456')
        self.usuario.user_permissions.set(Permission.objects.filter(content_type__app_label='lai'))
        Operador.objects.create(usuario=self.usuario, nome='Operador Fictício', cargo='Operador',
                                email='op@example.invalid', acesso_global=True)
        self.client.force_login(self.usuario)
        self.token = ponte_extensao.gerar_token(self.usuario)

    def cabecalho(self):
        return {'HTTP_AUTHORIZATION': 'Bearer ' + self.token}

    def api(self, nome, dados=None, **extra):
        corpo = json.dumps(dados or {})
        return self.client.post(reverse('lai:' + nome), corpo, content_type='application/json',
                                **dict(self.cabecalho(), **extra))

    def registro(self, **extra):
        dados = dict(nup=NUP, assunto='Quadro de cargos', cadastro=date(2026, 9, 29), prazo=date(2026, 11, 3), link=LINK)
        dados.update(extra)
        return ManifestacaoFalabr.objects.create(**dados)

    def iniciar_pastas(self, *registros):
        resp = self.client.post(reverse('lai:automacao_iniciar'), {'selecionados': [r.pk for r in registros]})
        return resp


class TokenTest(_Base):
    def test_token_volta_ao_usuario(self):
        self.assertEqual(ponte_extensao.usuario_do_token(self.token), self.usuario)

    def test_lixo_e_token_de_outro_segredo_sao_recusados(self):
        self.assertIsNone(ponte_extensao.usuario_do_token(''))
        self.assertIsNone(ponte_extensao.usuario_do_token('abc.def.ghi'))
        self.assertIsNone(ponte_extensao.usuario_do_token(self.token + 'x'))

    def test_trocar_a_senha_invalida_o_token(self):
        self.usuario.set_password('outra-senha-123456')
        self.usuario.save()
        self.assertIsNone(ponte_extensao.usuario_do_token(self.token))

    def test_usuario_inativo_e_recusado(self):
        self.usuario.is_active = False
        self.usuario.save()
        self.assertIsNone(ponte_extensao.usuario_do_token(self.token))


class PacoteTest(_Base):
    def test_pacote_aponta_para_o_sistema_e_traz_o_codigo(self):
        pacote = zipfile.ZipFile(io.BytesIO(ponte_extensao.montar_pacote('https://sistema.example/', self.usuario)))
        nomes = set(pacote.namelist())
        self.assertTrue({'manifest.json', 'config.js', 'background.js', 'ponte.js', 'popup.html', 'popup.js'} <= nomes)
        manifesto = json.loads(pacote.read('manifest.json'))
        self.assertEqual(manifesto['manifest_version'], 3)
        self.assertIn('https://sistema.example/*', manifesto['host_permissions'])
        self.assertIn('https://falabr.cgu.gov.br/*', manifesto['host_permissions'])
        self.assertEqual(manifesto['content_scripts'][0]['matches'], ['https://sistema.example/lai/*'])
        config = pacote.read('config.js').decode()
        self.assertIn(self.token, config)
        self.assertIn('https://sistema.example', config)

    def test_baixar_pelo_sistema_usa_o_endereco_acessado(self):
        resp = self.client.get(reverse('lai:extensao_baixar'), HTTP_HOST='localhost')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/zip')
        pacote = zipfile.ZipFile(io.BytesIO(resp.content))
        self.assertIn('http://localhost/lai/*', pacote.read('manifest.json').decode())

    def test_atras_de_proxy_usa_https(self):
        with override_settings(ALLOWED_HOSTS=['*'], LAI_PUBLIC_URL='https://controladoria.example/lai/'):
            publico = self.client.get(reverse('lai:extensao_baixar'), HTTP_HOST='controladoria.example')
            encaminhado = self.client.get(reverse('lai:extensao_baixar'), HTTP_HOST='interno.example',
                                          HTTP_X_FORWARDED_PROTO='https')
        self.assertIn('https://controladoria.example/lai/*', zipfile.ZipFile(io.BytesIO(publico.content)).read('manifest.json').decode())
        self.assertIn('https://interno.example/lai/*', zipfile.ZipFile(io.BytesIO(encaminhado.content)).read('manifest.json').decode())

    def test_baixar_exige_login(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse('lai:extensao_baixar')).status_code, 302)

    def test_pagina_de_instrucoes(self):
        texto = self.client.get(reverse('lai:extensao')).content.decode()
        self.assertIn('Carregar sem pacote', texto)
        self.assertIn('Baixar a extensão', texto)

    def test_pagina_de_acompanhamento_pede_a_extensao(self):
        self.registro()
        texto = self.client.get(reverse('lai:pendentes')).content.decode()
        self.assertIn('Instalar a extensão', texto)
        self.assertIn('Trazer NUPs', texto)
        self.assertIn('Abrir o Fala.BR', texto)
        self.assertIn('Baixar pastas (.zip)', texto)
        self.assertNotIn('name="acao" value="logar"', texto)


class AcessoDaApiTest(_Base):
    def test_sem_codigo_ou_com_codigo_ruim(self):
        sem = self.client.post(reverse('lai:ext_ping'), '{}', content_type='application/json')
        self.assertEqual(sem.status_code, 401)
        ruim = self.client.post(reverse('lai:ext_ping'), '{}', content_type='application/json',
                                HTTP_AUTHORIZATION='Bearer lixo')
        self.assertEqual(ruim.status_code, 401)

    def test_get_nao_vale(self):
        self.assertEqual(self.client.get(reverse('lai:ext_ping'), **self.cabecalho()).status_code, 405)

    def test_codigo_bom_passa_sem_csrf(self):
        from django.test import Client
        cliente = Client(enforce_csrf_checks=True)
        resp = cliente.post(reverse('lai:ext_ping'), '{}', content_type='application/json', **self.cabecalho())
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['ok'])

    def test_modulo_exclusivo_do_administrador_recusa_quem_nao_e(self):
        with override_settings(LAI_SOMENTE_ADMIN=True):
            resp = self.api('ext_ping')
        self.assertEqual(resp.status_code, 403)

    def test_administrador_passa_quando_o_modulo_e_exclusivo(self):
        admin = get_user_model().objects.create_superuser('chefe', 'chefe@example.invalid', 'teste-lai-123456')
        self.client.logout()   # a extensão não leva cookie de sessão: só o código
        with override_settings(LAI_SOMENTE_ADMIN=True):
            resp = self.client.post(reverse('lai:ext_ping'), '{}', content_type='application/json',
                                    HTTP_AUTHORIZATION='Bearer ' + ponte_extensao.gerar_token(admin))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['usuario'], 'chefe')

    def test_corpo_que_nao_e_json(self):
        resp = self.client.post(reverse('lai:ext_leitura'), 'não é json', content_type='application/json', **self.cabecalho())
        self.assertEqual(resp.status_code, 400)


class TrazerPelaExtensaoTest(_Base):
    def test_fluxo_completo(self):
        resp = self.client.post(reverse('lai:trazer_iniciar'))
        self.assertTrue(resp.json()['ok'])
        self.assertTrue(self.client.get(reverse('lai:automacao_estado')).json()['rodando'])
        leitura = {'base': {'tipoFormulario': '3', 'ouvidoriaDestino': '3996'}, 'grupos': {
            'abertas': {'cab': CAB, 'linhas': [_linha(NUP), _linha(NUP)], 'total': 1},
            'encerradas': {'cab': CAB, 'linhas': [_linha('03996.2026.000777-00', situacao='Concluída')], 'total': 1}}}
        retorno = self.api('ext_leitura', leitura)
        self.assertEqual(retorno.status_code, 200)
        self.assertIn('1 aberta(s) e 1 encerrada(s)', retorno.json()['resumo'])
        self.assertEqual(ManifestacaoFalabr.objects.count(), 2)
        gravado = ManifestacaoFalabr.objects.get(nup=NUP)
        self.assertEqual(gravado.fila, 'ABERTA')
        self.assertEqual(gravado.prazo.isoformat(), '2026-11-03')
        estado = self.client.get(reverse('lai:automacao_estado')).json()
        self.assertFalse(estado['rodando'])
        self.assertIn('1 aberta(s)', estado['resumo'])
        # o órgão fica guardado para a próxima vez
        self.assertEqual(self.client.post(reverse('lai:trazer_iniciar')).json()['base']['ouvidoriaDestino'], '3996')

    def test_email_do_manifestante_nao_e_guardado(self):
        self.client.post(reverse('lai:trazer_iniciar'))
        self.api('ext_leitura', {'grupos': {'abertas': {'cab': CAB, 'linhas': [_linha(NUP)], 'total': 1}}})
        dados = list(ManifestacaoFalabr.objects.values())
        self.assertNotIn('cidadao@example.invalid', json.dumps(dados, default=str))

    def test_lista_vazia_e_recusada(self):
        self.client.post(reverse('lai:trazer_iniciar'))
        resp = self.api('ext_leitura', {'grupos': {'abertas': {'cab': CAB, 'linhas': [], 'total': 0}}})
        self.assertEqual(resp.status_code, 409)
        self.assertIn('não devolveu manifestações', resp.json()['erro'])

    def test_lista_incompleta_avisa(self):
        self.client.post(reverse('lai:trazer_iniciar'))
        resp = self.api('ext_leitura', {'grupos': {'abertas': {'cab': CAB, 'linhas': [_linha(NUP)], 'total': 5}}})
        self.assertIn('leia de novo para completar', resp.json()['resumo'])

    def test_nao_inicia_com_outra_tarefa_rodando(self):
        self.client.post(reverse('lai:trazer_iniciar'))
        resp = self.client.post(reverse('lai:trazer_iniciar'))
        self.assertEqual(resp.status_code, 409)

    def test_get_nao_inicia(self):
        self.assertEqual(self.client.get(reverse('lai:trazer_iniciar')).status_code, 405)


class PastasPelaExtensaoTest(_Base):
    def pasta_base(self):
        return Path(self._tmp.name) / 'pedidos' / '2026'

    def test_fluxo_completo_cria_a_pasta_com_pdf_e_anexos(self):
        registro = self.registro()
        resp = self.iniciar_pastas(registro)
        dados = resp.json()
        self.assertTrue(dados['ok'])
        self.assertEqual(dados['pendentes'], [{'nup': NUP, 'link': LINK}])
        self.assertEqual(dados['ja_prontos'], 0)

        self.assertTrue(self.api('ext_progresso', {'nup': NUP, 'atual': 1, 'etapa': 'Abrindo o pedido'}).json()['continuar'])
        enviado = self.client.post(reverse('lai:ext_pedido'), {
            'nup': NUP, 'pdf': io.BytesIO(PDF),
            'anexo': [io.BytesIO(_zip(**{'03996202600093610_pdf_1.pdf': PDF, 'planilha.xlsx': b'xlsx'}))],
        }, **self.cabecalho())
        self.assertEqual(enviado.status_code, 200, enviado.content)
        self.assertEqual(enviado.json()['anexos'], 2)
        self.assertEqual(self.api('ext_concluir').status_code, 200)

        pastas = [p for p in self.pasta_base().iterdir() if p.is_dir()]
        self.assertEqual(len(pastas), 1)
        pasta = pastas[0]
        self.assertTrue(pasta.name.startswith('1 - 03996.2026.000936-10 - QUADRO DE CARGOS'))
        nomes = {a.name for a in pasta.iterdir()}
        self.assertEqual(nomes, {'DetalhesNUP_03996202600093610.pdf', '03996.2026.000936-10_pdf_1.pdf', 'planilha.xlsx'})
        registro.refresh_from_db()
        self.assertEqual(registro.pasta, pasta.name)
        self.assertIsNotNone(registro.baixado_em)

        estado = self.client.get(reverse('lai:automacao_estado')).json()
        self.assertFalse(estado['rodando'])
        self.assertEqual(estado['resultados'][0]['anexos'], 2)
        self.assertTrue(estado['pode_baixar_zip'])
        self.assertNotIn('itens', estado)

    def test_baixar_zip_das_pastas(self):
        self.iniciar_pastas(self.registro())
        self.client.post(reverse('lai:ext_pedido'), {'nup': NUP, 'pdf': io.BytesIO(PDF)}, **self.cabecalho())
        self.api('ext_concluir')
        resp = self.client.get(reverse('lai:automacao_zip'))
        self.assertEqual(resp.status_code, 200)
        conteudo = b''.join(resp.streaming_content)
        nomes = zipfile.ZipFile(io.BytesIO(conteudo)).namelist()
        self.assertEqual(len(nomes), 1)
        self.assertTrue(nomes[0].endswith('DetalhesNUP_03996202600093610.pdf'))
        self.assertIn('03996.2026.000936-10', nomes[0])

    def test_zip_sem_pastas_prontas_da_404(self):
        self.assertEqual(self.client.get(reverse('lai:automacao_zip')).status_code, 404)

    def test_anexo_unico_que_nao_e_zip(self):
        self.iniciar_pastas(self.registro())
        resp = self.client.post(reverse('lai:ext_pedido'), {
            'nup': NUP, 'pdf': io.BytesIO(PDF), 'anexo': [io.BytesIO(PDF)]}, **self.cabecalho())
        self.assertEqual(resp.json()['anexos'], 1)

    def test_zip_com_caminho_malicioso_fica_dentro_da_pasta(self):
        self.iniciar_pastas(self.registro())
        resp = self.client.post(reverse('lai:ext_pedido'), {
            'nup': NUP, 'pdf': io.BytesIO(PDF),
            'anexo': [io.BytesIO(_zip(**{'../../fora.txt': b'x', 'dir/ok.pdf': PDF}))]}, **self.cabecalho())
        self.assertEqual(resp.status_code, 200)
        self.assertFalse((Path(self._tmp.name) / 'fora.txt').exists())
        self.assertFalse((self.pasta_base().parent / 'fora.txt').exists())
        pasta = next(p for p in self.pasta_base().iterdir() if p.is_dir())
        self.assertIn('fora.txt', {a.name for a in pasta.iterdir()})

    def test_arquivo_que_nao_e_pdf_e_recusado(self):
        self.iniciar_pastas(self.registro())
        resp = self.client.post(reverse('lai:ext_pedido'), {'nup': NUP, 'pdf': io.BytesIO(b'<html>erro</html>' * 30)},
                                **self.cabecalho())
        self.assertEqual(resp.status_code, 409)
        self.assertFalse(self.pasta_base().exists() and any(self.pasta_base().iterdir()))

    def test_pedido_fora_da_tarefa_e_recusado(self):
        resp = self.client.post(reverse('lai:ext_pedido'), {'nup': NUP, 'pdf': io.BytesIO(PDF)}, **self.cabecalho())
        self.assertEqual(resp.status_code, 409)
        self.iniciar_pastas(self.registro())
        outro = self.client.post(reverse('lai:ext_pedido'), {'nup': '03996.2026.000001-00', 'pdf': io.BytesIO(PDF)},
                                 **self.cabecalho())
        self.assertEqual(outro.status_code, 409)

    def test_falha_de_um_pedido_nao_derruba_os_outros(self):
        primeiro = self.registro()
        segundo = self.registro(nup='03996.2026.000937-90', assunto='Outro assunto')
        self.iniciar_pastas(primeiro, segundo)
        self.api('ext_falha', {'nup': NUP, 'erro': 'O Exportar não devolveu um PDF.'})
        self.client.post(reverse('lai:ext_pedido'), {'nup': '03996.2026.000937-90', 'pdf': io.BytesIO(PDF)}, **self.cabecalho())
        self.api('ext_concluir')
        estado = self.client.get(reverse('lai:automacao_estado')).json()
        por_nup = {r['nup']: r for r in estado['resultados']}
        self.assertEqual(por_nup[NUP]['erro'], 'O Exportar não devolveu um PDF.')
        self.assertFalse(por_nup[NUP]['pdf'])
        self.assertTrue(por_nup['03996.2026.000937-90']['pdf'])
        self.assertEqual(ManifestacaoFalabr.objects.get(nup=NUP).pasta, '')

    def test_sequencia_das_pastas_segue_a_ordem_do_nup(self):
        a = self.registro(nup='03996.2026.000938-70', assunto='B')
        b = self.registro(nup='03996.2026.000937-90', assunto='A')
        dados = self.iniciar_pastas(a, b).json()
        self.assertEqual([p['nup'] for p in dados['pendentes']], ['03996.2026.000937-90', '03996.2026.000938-70'])
        for nup in ('03996.2026.000937-90', '03996.2026.000938-70'):
            self.client.post(reverse('lai:ext_pedido'), {'nup': nup, 'pdf': io.BytesIO(PDF)}, **self.cabecalho())
        nomes = sorted(p.name for p in self.pasta_base().iterdir())
        self.assertTrue(nomes[0].startswith('1 - 03996.2026.000937-90'))
        self.assertTrue(nomes[1].startswith('2 - 03996.2026.000938-70'))

    def test_pedido_que_ja_tem_pdf_nao_e_baixado_de_novo(self):
        registro = self.registro()
        self.iniciar_pastas(registro)
        self.client.post(reverse('lai:ext_pedido'), {'nup': NUP, 'pdf': io.BytesIO(PDF)}, **self.cabecalho())
        self.api('ext_concluir')
        outra_vez = self.iniciar_pastas(registro).json()
        self.assertEqual(outra_vez['pendentes'], [])
        self.assertEqual(outra_vez['ja_prontos'], 1)
        estado = self.client.get(reverse('lai:automacao_estado')).json()
        self.assertFalse(estado['rodando'])
        self.assertTrue(estado['resultados'][0]['ja_baixado'])

    def test_erro_da_extensao_encerra_a_tarefa(self):
        self.iniciar_pastas(self.registro())
        resp = self.api('ext_progresso', {'erro': 'O login no Fala.BR expirou.', 'fim': True})
        self.assertFalse(resp.json()['continuar'])
        estado = self.client.get(reverse('lai:automacao_estado')).json()
        self.assertFalse(estado['rodando'])
        self.assertEqual(estado['erro'], 'O login no Fala.BR expirou.')

    def test_cancelar_pela_tela_manda_a_extensao_parar(self):
        self.iniciar_pastas(self.registro())
        self.client.post(reverse('lai:automacao_cancelar'), {'motivo': 'A extensão não respondeu.'})
        self.assertFalse(self.api('ext_progresso', {'etapa': 'x'}).json()['continuar'])
        self.assertEqual(self.client.get(reverse('lai:automacao_estado')).json()['erro'], 'A extensão não respondeu.')

    def test_tarefa_sem_sinal_da_extensao_conta_como_parada(self):
        self.iniciar_pastas(self.registro())
        caminho = ponte_extensao._arquivo()
        dados = json.loads(caminho.read_text(encoding='utf-8'))
        dados['atualizado'] = time.time() - 10000
        caminho.write_text(json.dumps(dados), encoding='utf-8')
        estado = self.client.get(reverse('lai:automacao_estado')).json()
        self.assertFalse(estado['rodando'])
        self.assertIn('parou de responder', estado['erro'])
        # e a tela pode iniciar outra tarefa
        self.assertTrue(self.client.post(reverse('lai:trazer_iniciar')).json()['ok'])

    def test_nao_inicia_pasta_com_outra_tarefa_rodando(self):
        self.client.post(reverse('lai:trazer_iniciar'))
        resp = self.iniciar_pastas(self.registro())
        self.assertEqual(resp.status_code, 409)

    def test_pedido_sem_link_do_falabr_nao_inicia(self):
        resp = self.iniciar_pastas(self.registro(link='https://outro.example/x'))
        self.assertEqual(resp.status_code, 409)

    @override_settings(LAI_PLANILHA_ATIVA=True, LAI_PLANILHA_NOME='controle.xlsx', LAI_PLANILHA_ABA='FALA BR')
    def test_planilha_e_preenchida_ao_concluir_quando_ligada(self):
        from openpyxl import Workbook
        self.pasta_base().mkdir(parents=True)
        livro = Workbook()
        livro.active.title = 'FALA BR'
        livro.save(self.pasta_base() / 'controle.xlsx')
        self.iniciar_pastas(self.registro())
        self.client.post(reverse('lai:ext_pedido'), {'nup': NUP, 'pdf': io.BytesIO(PDF)}, **self.cabecalho())
        self.api('ext_concluir')
        estado = self.client.get(reverse('lai:automacao_estado')).json()
        self.assertEqual(estado['planilha_erro'], '')
        self.assertTrue(estado['planilha'])
        self.assertEqual(estado['resultados'][0]['planilha'], 'linha 4')

    def test_telas_exigem_login(self):
        self.client.logout()
        for nome in ('automacao_estado', 'automacao_zip', 'extensao'):
            self.assertEqual(self.client.get(reverse('lai:' + nome)).status_code, 302)
        for nome in ('trazer_iniciar', 'automacao_iniciar', 'automacao_cancelar'):
            self.assertEqual(self.client.post(reverse('lai:' + nome)).status_code, 302)
