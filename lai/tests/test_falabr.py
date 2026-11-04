import json
import urllib.error
from io import BytesIO
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings
from django.urls import reverse
from lai import acompanhamento, falabr
from lai.models import ManifestacaoFalabr, Operador
from lai import ponte_extensao
from lai.navegador_falabr import _linhas_da_tabela, protocolos_no_texto

CREDENCIAIS = dict(
    LAI_FALABR_BASE='https://falabr.example',
    LAI_FALABR_CLIENT_ID='cliente-lai',
    LAI_FALABR_CLIENT_SECRET='segredo-lai',
    LAI_FALABR_USERNAME='app.orgao',
    LAI_FALABR_PASSWORD='senha-super-secreta',
)

class _Resp:
    def __init__(self, payload):
        self.payload = payload
    def read(self):
        return json.dumps(self.payload).encode()
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False

def _urlopen(req, timeout=0):
    url = req.full_url
    if url.endswith('/oauth/token'):
        return _Resp({'access_token': 'tok-teste'})
    if url.endswith('/api/tipos-formulario'):
        return _Resp([
            {'IdTipoFormulario': 1, 'DescTipoFormulario': 'Padrão'},
            {'IdTipoFormulario': 3, 'DescTipoFormulario': 'Acesso à Informação'},
        ])
    if 'IdSituacaoManifestacao=1' in url:
        return _Resp([{
            'IdManifestacao': 10,
            'NumerosProtocolo': ['00000.2026.000099-00'],
            'Assunto': {'DescAssunto': 'Quadro de servidores'},
            'Situacao': {'DescSituacaoManifestacao': 'Cadastrada'},
            'DataCadastro': '01/10/2026',
            'PrazoAtendimento': '21/10/2026',
            'EmailManifestante': 'cidadao@example.invalid',
            'CodigoAcesso': 'SEGREDO-DE-ACESSO',
        }])
    raise urllib.error.HTTPError(url, 404, 'not found', hdrs=None, fp=BytesIO(b''))

@override_settings(LAI_SOMENTE_ADMIN=False)
class ProtocolosNaTelaTest(TestCase):
    def test_reconhece_nup_e_ignora_cpf(self):
        texto = 'Pedido 00106.000123/2026-81 e também 00000.2026.000099-00. CPF 123.456.789-00.'
        self.assertEqual(protocolos_no_texto(texto), ['00106.000123/2026-81', '00000.2026.000099-00'])

@override_settings(**CREDENCIAIS)
@override_settings(LAI_SOMENTE_ADMIN=False)
class FalabrClienteTest(TestCase):
    def setUp(self):
        falabr.limpar_cache()
    def test_lista_so_campos_operacionais(self):
        with patch('lai.falabr.urllib.request.urlopen', side_effect=_urlopen):
            rows = falabr.listar_pendentes()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['nup'], '00000.2026.000099-00')
        self.assertEqual(rows[0]['assunto'], 'Quadro de servidores')
        self.assertNotIn('EmailManifestante', rows[0])
        self.assertNotIn('SEGREDO-DE-ACESSO', json.dumps(rows))
    def test_erro_nao_repete_senha(self):
        def falha(req, timeout=0):
            corpo = json.dumps({'error_description': 'senha-super-secreta invalida'}).encode()
            raise urllib.error.HTTPError(req.full_url, 400, 'bad', hdrs=None, fp=BytesIO(corpo))
        with patch('lai.falabr.urllib.request.urlopen', side_effect=falha):
            with self.assertRaises(falabr.FalabrError) as ctx:
                falabr.listar_pendentes()
        self.assertNotIn('senha-super-secreta', str(ctx.exception))

@override_settings(LAI_SOMENTE_ADMIN=False)
class FalabrPaginaTest(TestCase):
    def setUp(self):
        usuario = get_user_model().objects.create_user('operador', password='teste-lai-123456')
        usuario.user_permissions.set(Permission.objects.filter(content_type__app_label='lai'))
        Operador.objects.create(usuario=usuario, nome='Operador Fictício', cargo='Operador', email='op@example.invalid', acesso_global=True)
        self.client.force_login(usuario)
    def test_pagina_sem_credencial_explica_o_proximo_passo(self):
        falabr.limpar_cache()
        resp = self.client.get(reverse('lai:pendentes'))
        self.assertEqual(resp.status_code, 200)
        texto = resp.content.decode()
        self.assertIn('Instalar a extensão', texto)
        self.assertIn('Trazer NUPs', texto)
        self.assertNotIn('>Logar<', texto)
        self.assertNotIn('Buscar NUPs', texto)
        self.assertNotIn('00000.2026.000099-00', texto)
    def test_abrir_usa_navegador_comum(self):
        with patch('lai.navegador_falabr._porta_responde', return_value=False), \
             patch('lai.navegador_falabr._encerrar_perfil'), \
             patch('lai.navegador_falabr._esperar_porta'), \
             patch('lai.navegador_falabr._executavel', return_value='msedge.exe'), \
             patch('lai.navegador_falabr.subprocess.Popen') as abrir_janela:
            from lai import navegador_falabr
            navegador_falabr.abrir()
        linha = abrir_janela.call_args.args[0]
        self.assertIn('https://falabr.cgu.gov.br/', linha)
        self.assertTrue(any(item.startswith('--user-data-dir=') for item in linha))
        self.assertNotIn('--enable-automation', linha)
        self.assertNotIn('--headless', linha)
    def test_sessao_online_so_com_nome_no_botao_do_falabr(self):
        from lai import navegador_falabr
        self.assertIn('#avatar-sign-in', navegador_falabr._USUARIO_JS)
        with patch('lai.navegador_falabr._porta_responde', return_value=False):
            self.assertFalse(navegador_falabr.sessao()['online'])
    @override_settings(**CREDENCIAIS)
    def test_pagina_mostra_nup_sem_dado_pessoal(self):
        falabr.limpar_cache()
        with patch('lai.falabr.urllib.request.urlopen', side_effect=_urlopen):
            resp = self.client.get(reverse('lai:pendentes'))
        texto = resp.content.decode()
        self.assertEqual(resp.status_code, 200)
        self.assertIn('00000.2026.000099-00', texto)
        self.assertIn('Ainda não importada', texto)
        self.assertNotIn('cidadao@example.invalid', texto)
        self.assertNotIn('SEGREDO-DE-ACESSO', texto)
        self.assertNotIn('senha-super-secreta', texto)


CABECALHO = ['Número', 'Órgão Destinatário', 'Assunto', 'Serviço', 'Tipo',
             'E-mail do manifestante', 'Cadastro', 'Prazo', 'Situação', 'Responsável']


def _celulas(*valores, href=''):
    return [{'texto': v, 'href': href if i == 0 else ''} for i, v in enumerate(valores)]


@override_settings(LAI_SOMENTE_ADMIN=False)
class LeituraDaTabelaTest(TestCase):
    def test_le_colunas_e_ignora_email(self):
        dados = {'cab': CABECALHO, 'linhas': [
            _celulas('03996.2026.000936-10', 'Prefeitura', 'Quadro de cargos', '', 'Acesso à Informação',
                     'cidadao@example.invalid', '29/09/2026', '03/11/2026', 'Prorrogada', 'Fulana',
                     href='https://falabr.example/web/manifestacao/detalhar/1'),
            _celulas('sem número aqui', 'x', '', '', '', '', '', '', '', ''),
        ]}
        linhas = _linhas_da_tabela(dados)
        self.assertEqual(len(linhas), 1)
        linha = linhas[0]
        self.assertEqual(linha['nup'], '03996.2026.000936-10')
        self.assertEqual(linha['nup_normalizada'], '03996202600093610')
        self.assertEqual(linha['prazo'], '03/11/2026')
        self.assertEqual(linha['cadastro'], '29/09/2026')
        self.assertEqual(linha['situacao'], 'Prorrogada')
        self.assertEqual(linha['assunto'], 'Quadro de cargos')
        self.assertTrue(linha['link'].endswith('/detalhar/1'))
        self.assertNotIn('cidadao@example.invalid', json.dumps(linha))

    def test_tabela_sem_prazo_nao_vira_lista(self):
        self.assertEqual(_linhas_da_tabela({'cab': ['Número', 'Assunto'], 'linhas': []}), [])


@override_settings(LAI_SOMENTE_ADMIN=False)
class AcompanhamentoFalabrTest(TestCase):
    def setUp(self):
        usuario = get_user_model().objects.create_user('operador', password='teste-lai-123456')
        usuario.user_permissions.set(Permission.objects.filter(content_type__app_label='lai'))
        Operador.objects.create(usuario=usuario, nome='Operador Fictício', cargo='Operador',
                                email='op@example.invalid', acesso_global=True)
        self.client.force_login(usuario)

    def _linha(self, **extra):
        base = {'nup': '03996.2026.000936-10', 'assunto': 'Quadro de cargos', 'tipo': 'Acesso à Informação',
                'cadastro': '29/09/2026', 'prazo': '03/11/2026', 'situacao': 'Cadastrada',
                'responsavel': 'Fulana', 'link': 'https://falabr.example/detalhar/1'}
        base.update(extra)
        return base

    def test_grava_e_detecta_mudanca_de_prazo(self):
        primeiro = acompanhamento.sincronizar([self._linha()])
        self.assertEqual(primeiro, {'total': 1, 'novas': 1, 'alteradas': 0})
        segundo = acompanhamento.sincronizar([self._linha(prazo='18/11/2026', situacao='Prorrogada')])
        self.assertEqual(segundo, {'total': 1, 'novas': 0, 'alteradas': 1})
        obj = ManifestacaoFalabr.objects.get()
        self.assertEqual(obj.prazo.isoformat(), '2026-11-18')
        self.assertEqual(obj.prazo_anterior.isoformat(), '2026-11-03')
        self.assertEqual(obj.situacao_anterior, 'Cadastrada')
        self.assertIsNotNone(obj.alterado_em)

    def test_leitura_vazia_nao_apaga_dados(self):
        acompanhamento.sincronizar([self._linha()])
        acompanhamento.sincronizar([self._linha(assunto='', prazo='', situacao='', tipo='')])
        obj = ManifestacaoFalabr.objects.get()
        self.assertEqual(obj.assunto, 'Quadro de cargos')
        self.assertEqual(obj.prazo.isoformat(), '2026-11-03')
        self.assertEqual(obj.situacao, 'Cadastrada')
        self.assertIsNone(obj.alterado_em)

    def test_ignora_numero_incompleto(self):
        resultado = acompanhamento.sincronizar([self._linha(nup='1234')])
        self.assertEqual(resultado['total'], 0)
        self.assertFalse(ManifestacaoFalabr.objects.exists())

    def _leitura(self, abertas=(), encerradas=(), completa=True):
        return {'grupos': {
            'abertas': {'linhas': list(abertas), 'total': len(abertas), 'completa': completa},
            'encerradas': {'linhas': list(encerradas), 'total': len(encerradas), 'completa': True},
        }}

    def test_leitura_gravada_mostra_prazo(self):
        lido = self._leitura(abertas=[dict(self._linha(), nup_normalizada='03996202600093610')])
        gravado = acompanhamento.sincronizar_leitura(lido)
        self.assertIn('1 aberta(s) e 0 encerrada(s) lida(s)', ponte_extensao.resumo_da_leitura(gravado))
        texto = self.client.get(reverse('lai:pendentes')).content.decode()
        self.assertIn('03996.2026.000936-10', texto)
        self.assertIn('03/11/2026', texto)
        self.assertIn('Ainda não importada', texto)
        self.assertIn('Cadastrar', texto)

    def test_aviso_quando_lista_incompleta(self):
        lido = self._leitura(abertas=[self._linha()], completa=False)
        gravado = acompanhamento.sincronizar_leitura(lido)
        self.assertIn('leia de novo para completar', ponte_extensao.resumo_da_leitura(gravado))

    def test_encerradas_ficam_fora_das_abertas_e_aparecem_no_filtro(self):
        encerrada = self._linha(nup='03996.2026.000777-00', situacao='Concluída', prazo='01/10/2026')
        acompanhamento.sincronizar_leitura(self._leitura(abertas=[self._linha()], encerradas=[encerrada]))
        padrao = self.client.get(reverse('lai:pendentes')).content.decode()
        self.assertIn('03996.2026.000936-10', padrao)
        self.assertNotIn('03996.2026.000777-00', padrao)
        so_encerradas = self.client.get(reverse('lai:pendentes') + '?filtro=encerradas').content.decode()
        self.assertIn('03996.2026.000777-00', so_encerradas)
        self.assertNotIn('Vencido há', so_encerradas)

    def test_pedido_que_some_da_fila_aberta_e_marcado(self):
        outra = self._linha(nup='03996.2026.000555-00')
        acompanhamento.sincronizar_leitura(self._leitura(abertas=[self._linha(), outra]))
        resultado = acompanhamento.sincronizar_leitura(self._leitura(abertas=[self._linha()]))
        self.assertEqual(resultado['saiu'], 1)
        self.assertEqual(ManifestacaoFalabr.objects.get(nup='03996.2026.000555-00').fila, 'SAIU')

    def test_pedido_que_passou_para_encerrada_nao_vira_saiu(self):
        outra = self._linha(nup='03996.2026.000555-00')
        acompanhamento.sincronizar_leitura(self._leitura(abertas=[self._linha(), outra]))
        resultado = acompanhamento.sincronizar_leitura(self._leitura(
            abertas=[self._linha()], encerradas=[dict(outra, situacao='Concluída')]))
        self.assertEqual(resultado['saiu'], 0)
        obj = ManifestacaoFalabr.objects.get(nup='03996.2026.000555-00')
        self.assertEqual(obj.fila, 'ENCERRADA')
        self.assertEqual(obj.situacao_anterior, 'Cadastrada')

    def test_leitura_incompleta_nao_marca_saidas(self):
        acompanhamento.sincronizar_leitura(self._leitura(abertas=[self._linha(), self._linha(nup='03996.2026.000555-00')]))
        resultado = acompanhamento.sincronizar_leitura(self._leitura(abertas=[self._linha()], completa=False))
        self.assertEqual(resultado['saiu'], 0)
        self.assertTrue(resultado['incompleta'])

    def test_faixas_de_acompanhamento(self):
        from datetime import date
        hoje = date(2026, 11, 3)
        def item(n, prazo, situacao='Cadastrada', fila='ABERTA'):
            return {'nup': f'03996.2026.00000{n}-00', 'nup_normalizada': f'0399620260000{n}00',
                    'prazo': prazo, 'situacao': situacao, 'fila': fila}
        itens = acompanhamento.montar_lista([
            item(1, '02/11/2026'), item(2, '03/11/2026'), item(3, '07/11/2026'), item(4, '20/11/2026'),
            item(5, '05/11/2026', 'Complementação Solicitada'), item(6, '01/10/2026', 'Concluída', 'ENCERRADA'),
            item(7, '', 'Cadastrada'), item(8, '10/11/2026', 'Prorrogada')], [], hoje)
        faixas = {i['nup'][-4:-3]: i['faixa'] for i in itens}
        self.assertEqual(faixas, {'1': 'vencida', '2': 'hoje', '3': 'urgente', '4': 'no_prazo',
                                  '5': 'aguardando', '6': 'encerrada', '7': 'sem_prazo', '8': 'no_prazo'})
        self.assertEqual([i['nup'][-4:-3] for i in acompanhamento.filtrar(itens, 'prorrogadas')], ['8'])
        valores = {c['filtro']: c['valor'] for c in acompanhamento.resumo(itens)}
        self.assertEqual((valores['abertas'], valores['vencidas'], valores['hoje'], valores['urgentes'],
                          valores['encerradas']), (7, 1, 1, 1, 1))

    def test_busca_por_numero_e_assunto(self):
        acompanhamento.sincronizar([self._linha(), self._linha(nup='03996.2026.000555-00', assunto='Merenda escolar')])
        pagina = self.client.get(reverse('lai:pendentes') + '?q=merenda').content.decode()
        self.assertIn('03996.2026.000555-00', pagina)
        self.assertNotIn('03996.2026.000936-10', pagina)
        pagina = self.client.get(reverse('lai:pendentes') + '?q=000936').content.decode()
        self.assertIn('03996.2026.000936-10', pagina)
        self.assertNotIn('03996.2026.000555-00', pagina)

    def test_demanda_respondida_no_modulo_mas_aberta_no_fala_br_e_sinalizada(self):
        from datetime import date
        from lai.models import Demanda, PoliticaPrazo, Secretaria
        secretaria = Secretaria.objects.create(nome='Administração', sigla='ADM', email='adm@example.invalid')
        Demanda.objects.create(
            nup='03996.2026.000936-10', tipo='Acesso à Informação', cadastro_falabr=date(2026, 9, 29),
            marco_inicial=date(2026, 9, 29), vencimento_original=date(2026, 11, 3),
            prazo_interno=date(2026, 10, 30), teor='t', resumo='r', secretaria=secretaria,
            operador=Operador.objects.get(), politica=PoliticaPrazo.objects.create(versao='Teste v1'),
            status='RESPOSTA_INTERNA')
        acompanhamento.sincronizar([self._linha()])
        pagina = self.client.get(reverse('lai:pendentes') + '?filtro=divergencias').content.decode()
        self.assertIn('Falta registrar a resposta no Fala.BR', pagina)

    def test_exporta_csv_da_faixa(self):
        acompanhamento.sincronizar([self._linha(assunto='=SOMA(1;1)')])
        resp = self.client.get(reverse('lai:exportar_falabr') + '?filtro=abertas')
        self.assertEqual(resp.status_code, 200)
        corpo = resp.content.decode('utf-8-sig')
        self.assertIn('03996.2026.000936-10', corpo)
        self.assertIn("'=SOMA(1;1)", corpo)
        self.assertNotIn('cidadao@example.invalid', corpo)

    def test_mostra_mudanca_de_prazo(self):
        acompanhamento.sincronizar([self._linha()])
        acompanhamento.sincronizar([self._linha(prazo='18/11/2026', situacao='Prorrogada')])
        texto = self.client.get(reverse('lai:pendentes')).content.decode()
        self.assertIn('Prazo mudou de 03/11/2026 para 18/11/2026', texto)
        self.assertIn('Situação mudou de Cadastrada para Prorrogada', texto)

    def test_cadastro_vem_preenchido_da_leitura(self):
        acompanhamento.sincronizar([self._linha()])
        pk = ManifestacaoFalabr.objects.get().pk
        resp = self.client.get(reverse('lai:nova') + f'?falabr={pk}')
        self.assertEqual(resp.status_code, 200)
        form = resp.context['form']
        self.assertEqual(form.initial['nup'], '03996.2026.000936-10')
        self.assertEqual(form.initial['vencimento_original'].isoformat(), '2026-11-03')
        self.assertEqual(form.initial['cadastro_falabr'].isoformat(), '2026-09-29')
        self.assertEqual(form.initial['resumo'], 'Quadro de cargos')

    def test_prazo_diferente_do_modulo_e_sinalizado(self):
        from datetime import date
        from lai.models import Demanda, PoliticaPrazo, Secretaria
        secretaria = Secretaria.objects.create(nome='Administração', sigla='ADM', email='adm@example.invalid')
        politica = PoliticaPrazo.objects.create(versao='Teste v1')
        Demanda.objects.create(
            nup='03996.2026.000936-10', tipo='Acesso à Informação', cadastro_falabr=date(2026, 9, 29),
            marco_inicial=date(2026, 9, 29), vencimento_original=date(2026, 10, 19),
            prazo_interno=date(2026, 10, 15), teor='t', resumo='r', secretaria=secretaria,
            operador=Operador.objects.get(), politica=politica)
        acompanhamento.sincronizar([self._linha()])
        texto = self.client.get(reverse('lai:pendentes')).content.decode()
        self.assertIn('Já cadastrada', texto)
        self.assertIn('Prazo no módulo (19/10/2026) é diferente do Fala.BR', texto)

    def test_classe_e_texto_do_prazo(self):
        from datetime import date
        hoje = date(2026, 11, 3)
        itens = acompanhamento.montar_lista(
            [{'nup': '03996.2026.000001-00', 'nup_normalizada': '03996202600000100', 'prazo': '02/11/2026'},
             {'nup': '03996.2026.000002-00', 'nup_normalizada': '03996202600000200', 'prazo': '03/11/2026'},
             {'nup': '03996.2026.000003-00', 'nup_normalizada': '03996202600000300', 'prazo': '20/11/2026'}],
            [], hoje)
        self.assertEqual([i['dias_texto'] for i in itens], ['Vencido há 1 dia(s)', 'Vence hoje', '17 dias restantes'])
        self.assertEqual([i['classe'] for i in itens], ['vermelho', 'vermelho', ''])
