import io
import tempfile
import zipfile
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings
from django.urls import reverse
from openpyxl import Workbook, load_workbook

from lai import automacao_falabr, pastas_pedidos, planilha_controle, ponte_extensao
from lai.models import ManifestacaoFalabr, Operador
from lai.navegador_falabr import NavegadorError

NUP = '03996.2026.000716-40'


class _Download:
    def __init__(self, nome, conteudo):
        self.suggested_filename = nome
        self._conteudo = conteudo

    def save_as(self, caminho):
        Path(caminho).write_bytes(self._conteudo)


def _zip(arquivos):
    memoria = io.BytesIO()
    with zipfile.ZipFile(memoria, 'w') as pacote:
        for nome, dados in arquivos.items():
            pacote.writestr(nome, dados)
    return memoria.getvalue()


@override_settings(LAI_SOMENTE_ADMIN=False)
class PastasDosPedidosTest(TestCase):
    def test_nome_no_padrao_do_controle(self):
        self.assertEqual(
            pastas_pedidos.nome_da_pasta(77, NUP, 'despesas com receitas vinculadas petroleo - lei 12.858'),
            '77 - 03996.2026.000716-40 - DESPESAS COM RECEITAS VINCULADAS PETROLEO - LEI 12.858')

    def test_tema_troca_caracteres_invalidos_e_limita_tamanho(self):
        self.assertEqual(pastas_pedidos.tema_para_pasta('Relatório: receitas / 2026?'), 'RELATÓRIO_ RECEITAS _ 2026_')
        self.assertLessEqual(len(pastas_pedidos.tema_para_pasta('A' * 500)), pastas_pedidos.LIMITE_TEMA)
        self.assertEqual(pastas_pedidos.tema_para_pasta('  ...  '), 'SEM TEMA')
        nome = pastas_pedidos.nome_da_pasta(1, NUP, '../../fora')
        self.assertNotIn('/', nome)
        self.assertNotIn('\\', nome)
        with tempfile.TemporaryDirectory() as tmp:
            pasta, _, _ = pastas_pedidos.preparar_pasta(tmp, NUP, '../../fora', 1)
            self.assertEqual(pasta.parent, Path(tmp))

    def test_sugestao_de_tema_limpa_rotulo_saudacao_e_dados_pessoais(self):
        s = pastas_pedidos.sugerir_tema
        self.assertEqual(s('ASSUNTO: Notas técnicas dos estudos orçamentários'), 'Notas técnicas dos estudos orçamentários')
        self.assertEqual(s('Bom dia, prezados. Solicito o balancete analítico da despesa'),
                         'Solicito o balancete analítico da despesa')
        self.assertEqual(
            s('Assunto: Relatórios de produtividade da CHC — 21 a 31 de maio e junho de 2024 Com fundamento nos art. 5º'),
            'Relatórios de produtividade da CHC — 21 a 31 de maio e junho de 2024')
        self.assertEqual(
            s('Plataforma Integrada de Ouvidoria e Acesso à Informação\nDetalhes da Manifestação\n\n'
              'Assunto: Relatórios de produtividade do SimplesVet\n\nÀ Prefeitura Municipal de Saquarema/RJ — SAI'),
            'Relatórios de produtividade do SimplesVet')
        self.assertEqual(s('Assunto:\n Notas técnicas do orçamento\n\nCom fundamento na LAI'), 'Notas técnicas do orçamento')
        self.assertEqual(
            s('Documentos essenciais da aquisição de insumos veterinários — Processo nº 1.391/2026. Com fundamento na LAI'),
            'Documentos essenciais da aquisição de insumos veterinários — Processo nº 1.391/2026')
        self.assertNotIn('123', s('Solicito certidão do CPF 123.456.789-09 e envio para fulano@example.invalid'))
        self.assertNotIn('@', s('Contato fulano@example.invalid sobre contratos'))
        longo = s('palavra ' * 40)
        self.assertLessEqual(len(longo), pastas_pedidos.LIMITE_TEMA)
        self.assertFalse(longo.endswith(' '))
        self.assertEqual(s(''), '')
        self.assertEqual(s(None), '')

    def test_nome_do_pdf_e_do_anexo(self):
        self.assertEqual(pastas_pedidos.nome_do_pdf(NUP), 'DetalhesNUP_03996202600071640.pdf')
        self.assertEqual(pastas_pedidos.nome_do_anexo('03996202600071640_pdf_2.pdf', NUP), f'{NUP}_pdf_2.pdf')
        self.assertEqual(pastas_pedidos.nome_do_anexo('contrato.pdf', NUP), 'contrato.pdf')

    def test_sequencia_continua_do_maior_numero(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            self.assertEqual(pastas_pedidos.proxima_sequencia(base), 1)
            (base / '76 - 03996.2026.000715-60 - ALGO').mkdir()
            (base / '9 - 03996.2026.000001-00 - OUTRO').mkdir()
            (base / 'sem numero').mkdir()
            (base / '2026 - CONTROLE FALA.BR.xlsx').write_bytes(b'x')
            self.assertEqual(pastas_pedidos.proxima_sequencia(base), 77)

    def test_pasta_existente_e_reaproveitada_e_renomeada(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            pasta, criada, usada = pastas_pedidos.preparar_pasta(base, NUP, 'primeiro tema', 77)
            self.assertTrue(criada)
            self.assertEqual((usada, pasta.name), (77, f'77 - {NUP} - PRIMEIRO TEMA'))
            (pasta / 'arquivo.txt').write_text('x')
            pasta2, criada2, usada2 = pastas_pedidos.preparar_pasta(base, NUP, 'tema corrigido', 78)
            self.assertFalse(criada2)
            self.assertEqual((usada2, pasta2.name), (77, f'77 - {NUP} - TEMA CORRIGIDO'))
            self.assertTrue((pasta2 / 'arquivo.txt').exists())
            self.assertEqual(len([p for p in base.iterdir()]), 1)


@override_settings(LAI_SOMENTE_ADMIN=False)
class ArquivosDaAutomacaoTest(TestCase):
    def test_zip_de_anexos_vai_direto_na_pasta_com_nome_do_nup(self):
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            pacote = _zip({'03996202600071640_pdf_1.pdf': b'1', '../../fora.txt': b'2', 'sub/b.pdf': b'3',
                           '03996202600071640_pdf_1.pdf ': b'4'})
            total = automacao_falabr._guardar_anexos(_Download('todos.zip', pacote), pasta, NUP)
            nomes = sorted(p.name for p in pasta.iterdir())
            self.assertEqual(total, 4)
            self.assertIn(f'{NUP}_pdf_1.pdf', nomes)
            self.assertIn('fora.txt', nomes)
            self.assertIn('b.pdf', nomes)
            self.assertFalse((pasta.parent / 'fora.txt').exists())
            self.assertFalse(any(n.startswith('_baixado_') for n in nomes))
            self.assertFalse((pasta / 'anexos').exists())

    def test_anexo_unico_nao_zip_e_mantido(self):
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            total = automacao_falabr._guardar_anexos(_Download('../doc.pdf', b'%PDF-1.4 x'), pasta, NUP)
            self.assertEqual(total, 1)
            self.assertEqual([p.name for p in pasta.iterdir()], ['doc.pdf'])

    def test_iniciar_recusa_link_de_outro_site(self):
        with self.assertRaises(NavegadorError):
            automacao_falabr.iniciar([{'nup': NUP, 'link': 'https://outro.example/x'}])

    def test_iniciar_exige_janela_aberta(self):
        with patch('lai.navegador_falabr._porta_responde', return_value=False):
            with self.assertRaises(NavegadorError) as ctx:
                automacao_falabr.iniciar([{'nup': NUP, 'link': 'https://falabr.cgu.gov.br/web/manifestacao/detalhar/1'}])
        self.assertIn('Logar', str(ctx.exception))

    def test_iniciar_exige_estar_online(self):
        offline = {'online': False, 'nome': '', 'perfil': '', 'janela': True, 'verificado': True}
        with patch('lai.navegador_falabr._porta_responde', return_value=True), \
             patch('lai.navegador_falabr.sessao', return_value=offline):
            with self.assertRaises(NavegadorError) as ctx:
                automacao_falabr.iniciar([{'nup': NUP, 'link': 'https://falabr.cgu.gov.br/web/manifestacao/detalhar/1'}])
        self.assertIn('não está online', str(ctx.exception))

    def test_planilha_fica_desligada_por_padrao(self):
        from django.conf import settings
        self.assertFalse(settings.LAI_PLANILHA_ATIVA)

    def test_nao_inclui_dados_do_manifestante_por_padrao(self):
        self.assertFalse(automacao_falabr.INCLUIR_DADOS_MANIFESTANTE)


def _planilha_modelo(pasta, extras=()):
    livro = Workbook()
    folha = livro.active
    folha.title = 'FALA BR'
    folha['A1'] = 'CONTROLE FALA.BR'
    for coluna, titulo in enumerate(['NUP', 'RECEBIDO', 'OBJETO', 'PRAZO FINAL BR', 'ENVIADO PARA',
                                     'PRAZO DA SECRETARIA', 'RETORNO', 'ENVIO NO PORTAL', 'STATUS', 'OBSERVAÇÃO'], 1):
        folha.cell(3, coluna).value = titulo
    folha['A4'] = '03996.2026.000715-60'
    folha['B4'] = datetime(2026, 8, 21)
    folha['B4'].number_format = 'dd/mm/yyyy'
    folha['C4'] = 'RELATORIO'
    folha['I4'] = 'RESPONDIDO'
    for linha in extras:
        folha.append(linha)
    caminho = Path(pasta) / '2026 - CONTROLE FALA.BR.xlsx'
    livro.save(caminho)
    return caminho


@override_settings(LAI_SOMENTE_ADMIN=False)
class PlanilhaDeControleTest(TestCase):
    def _linha(self, nup=NUP, **extra):
        base = {'nup': nup, 'cadastro': date(2026, 8, 21), 'tema': 'despesas vinculadas',
                'prazo': date(2026, 9, 14)}
        base.update(extra)
        return base

    def test_preenche_na_copia_e_nao_toca_no_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = _planilha_modelo(tmp)
            antes = original.read_bytes()
            with override_settings(LAI_PASTA_ANO=Path(tmp), LAI_PLANILHA_MODO='copia'):
                resultado, arquivo = planilha_controle.adicionar([self._linha()])
            self.assertEqual(original.read_bytes(), antes)
            self.assertTrue(arquivo.name.endswith('- COPIA.xlsx'))
            self.assertEqual(resultado[NUP], {'linha': 5, 'nova': True})
            folha = load_workbook(arquivo)['FALA BR']
            self.assertEqual(folha['A5'].value, NUP)
            self.assertEqual(folha['B5'].value, datetime(2026, 8, 21))
            self.assertEqual(folha['C5'].value, 'DESPESAS VINCULADAS')
            self.assertEqual(folha['D5'].value, datetime(2026, 9, 14))
            self.assertEqual(folha['F5'].value, datetime(2026, 9, 10))
            self.assertEqual(folha['I5'].value, 'AGUARDA')
            for coluna in 'EGHJ':
                self.assertIsNone(folha[f'{coluna}5'].value)
            self.assertEqual(folha['B5'].number_format, 'dd/mm/yyyy')

    def test_nup_que_ja_existe_nao_e_alterado_nem_duplicado(self):
        with tempfile.TemporaryDirectory() as tmp:
            _planilha_modelo(tmp)
            with override_settings(LAI_PASTA_ANO=Path(tmp), LAI_PLANILHA_MODO='copia'):
                planilha_controle.adicionar([self._linha()])
                resultado, arquivo = planilha_controle.adicionar([self._linha(tema='outro tema')])
            self.assertEqual(resultado[NUP], {'linha': 5, 'nova': False})
            folha = load_workbook(arquivo)['FALA BR']
            self.assertEqual(folha['C5'].value, 'DESPESAS VINCULADAS')
            self.assertIsNone(folha['A6'].value)

    def test_tema_editado_atualiza_so_o_objeto_da_linha_existente(self):
        with tempfile.TemporaryDirectory() as tmp:
            _planilha_modelo(tmp)
            with override_settings(LAI_PASTA_ANO=Path(tmp), LAI_PLANILHA_MODO='copia'):
                planilha_controle.adicionar([self._linha()])
                arquivo = planilha_controle.caminho()
                livro = load_workbook(arquivo)
                livro['FALA BR']['I5'] = 'ENVIADO'
                livro.save(arquivo)
                resultado, _ = planilha_controle.adicionar([self._linha(tema='tema revisado', tema_manual=True)])
            self.assertTrue(resultado[NUP]['objeto_atualizado'])
            folha = load_workbook(arquivo)['FALA BR']
            self.assertEqual(folha['C5'].value, 'TEMA REVISADO')
            self.assertEqual(folha['I5'].value, 'ENVIADO')

    def test_varias_linhas_seguem_a_ordem(self):
        with tempfile.TemporaryDirectory() as tmp:
            _planilha_modelo(tmp)
            with override_settings(LAI_PASTA_ANO=Path(tmp), LAI_PLANILHA_MODO='copia'):
                resultado, _ = planilha_controle.adicionar(
                    [self._linha(), self._linha(nup='03996.2026.000717-21', prazo=None)])
            self.assertEqual(resultado['03996.2026.000717-21']['linha'], 6)

    def test_modo_original_faz_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = _planilha_modelo(tmp)
            with override_settings(LAI_PASTA_ANO=Path(tmp), LAI_PLANILHA_MODO='original'):
                _, arquivo = planilha_controle.adicionar([self._linha()])
            self.assertEqual(arquivo, original)
            self.assertEqual(len(list(Path(tmp).glob('*.bak-*.xlsx'))), 1)
            self.assertEqual(load_workbook(original)['FALA BR']['A5'].value, NUP)

    def test_erros_claros(self):
        with tempfile.TemporaryDirectory() as tmp:
            with override_settings(LAI_PASTA_ANO=Path(tmp)):
                with self.assertRaises(planilha_controle.PlanilhaErro) as ctx:
                    planilha_controle.adicionar([self._linha()])
            self.assertIn('não encontrada', str(ctx.exception))
            _planilha_modelo(tmp)
            with override_settings(LAI_PASTA_ANO=Path(tmp), LAI_PLANILHA_ABA='OUTRA'):
                with self.assertRaises(planilha_controle.PlanilhaErro) as ctx:
                    planilha_controle.adicionar([self._linha()])
            self.assertIn('OUTRA', str(ctx.exception))


@override_settings(LAI_SOMENTE_ADMIN=False)
class RotasDaAutomacaoTest(TestCase):
    def setUp(self):
        usuario = get_user_model().objects.create_user('operador', password='teste-lai-123456')
        usuario.user_permissions.set(Permission.objects.filter(content_type__app_label='lai'))
        Operador.objects.create(usuario=usuario, nome='Operador Fictício', cargo='Operador',
                                email='op@example.invalid', acesso_global=True)
        self.client.force_login(usuario)

    def _registro(self, **extra):
        dados = dict(nup='03996.2026.000936-10', assunto='Quadro de cargos', cadastro=date(2026, 9, 29),
                     prazo=date(2026, 11, 3), link='https://falabr.cgu.gov.br/web/manifestacao/detalhar/1')
        dados.update(extra)
        return ManifestacaoFalabr.objects.create(**dados)

    def test_sem_marcados_devolve_erro(self):
        resp = self.client.post(reverse('lai:automacao_iniciar'), {})
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()['ok'])

    def test_get_nao_inicia(self):
        self.assertEqual(self.client.get(reverse('lai:automacao_iniciar')).status_code, 405)

    def test_inicia_com_os_marcados_usando_o_tema(self):
        registro = self._registro(tema='Tema corrigido')
        with patch('lai.views.ponte_extensao.iniciar_pastas', return_value={'total': 1, 'ja_prontos': 0, 'pendentes': []}) as iniciar:
            resp = self.client.post(reverse('lai:automacao_iniciar'), {'selecionados': [registro.pk, 'abc']})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['ok'])
        self.assertEqual(resp.json()['total'], 1)
        item = iniciar.call_args.args[0][0]
        self.assertEqual((item['nup'], item['tema'], item['prazo']), ('03996.2026.000936-10', 'Tema corrigido', date(2026, 11, 3)))

    def test_sem_tema_editado_usa_o_assunto(self):
        registro = self._registro()
        with patch('lai.views.ponte_extensao.iniciar_pastas', return_value={'total': 1, 'ja_prontos': 0, 'pendentes': []}) as iniciar:
            self.client.post(reverse('lai:automacao_iniciar'), {'selecionados': [registro.pk]})
        self.assertEqual(iniciar.call_args.args[0][0]['tema'], 'Quadro de cargos')

    def test_erro_do_navegador_vira_mensagem(self):
        registro = self._registro()
        with patch('lai.views.ponte_extensao.iniciar_pastas', side_effect=ponte_extensao.ExtensaoError('Janela fechada')):
            resp = self.client.post(reverse('lai:automacao_iniciar'), {'selecionados': [registro.pk]})
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()['erro'], 'Janela fechada')

    def test_estado_devolve_json(self):
        resp = self.client.get(reverse('lai:automacao_estado'))
        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(resp.json(), dict)

    def test_lista_mostra_marcacao_botao_e_tema(self):
        self._registro()
        texto = self.client.get(reverse('lai:pendentes')).content.decode()
        self.assertIn('Automatizar pastas', texto)
        self.assertIn('Concluído!', texto)
        self.assertIn('name="selecionados"', texto)
        self.assertIn('Iniciando automatização', texto)
        self.assertIn('Baixar pastas (.zip)', texto)
        self.assertIn('Tema da pasta: QUADRO DE CARGOS', texto)

    def test_editar_tema(self):
        registro = self._registro()
        resp = self.client.post(reverse('lai:pendentes'),
                                {'acao': 'tema', 'pk': registro.pk, 'tema': '  novo   tema  ', 'filtro': 'abertas'})
        self.assertEqual(resp.status_code, 302)
        registro.refresh_from_db()
        self.assertEqual(registro.tema, 'novo tema')
        self.assertEqual(registro.tema_efetivo, 'novo tema')
        self.client.post(reverse('lai:pendentes'), {'acao': 'tema', 'pk': registro.pk, 'tema': ''})
        registro.refresh_from_db()
        self.assertEqual(registro.tema_efetivo, 'Quadro de cargos')

    def test_abrir_pasta_abre_a_pasta_configurada(self):
        with tempfile.TemporaryDirectory() as tmp, \
                override_settings(LAI_PASTA_ANO=Path(tmp) / '2026'), \
                patch('lai.views.os.name', 'nt'), \
                patch('lai.views.os.startfile', create=True) as abrir:
            resp = self.client.post(reverse('lai:automacao_abrir_pasta'))
            self.assertEqual(resp.status_code, 200)
            abrir.assert_called_once_with(str(Path(tmp) / '2026'))
            self.assertTrue((Path(tmp) / '2026').is_dir())

    def test_abrir_pasta_recusa_acesso_de_outro_computador(self):
        with patch('lai.views.os.name', 'nt'), patch('lai.views.os.startfile', create=True) as abrir:
            resp = self.client.post(reverse('lai:automacao_abrir_pasta'), REMOTE_ADDR='10.0.0.7')
        self.assertEqual(resp.status_code, 403)
        abrir.assert_not_called()

    def test_abrir_pasta_exige_post(self):
        self.assertEqual(self.client.get(reverse('lai:automacao_abrir_pasta')).status_code, 405)

    def test_estado_informa_se_pode_abrir_pasta(self):
        with patch('lai.views.os.name', 'nt'):
            self.assertTrue(self.client.get(reverse('lai:automacao_estado')).json()['pode_abrir_pasta'])
            remoto = self.client.get(reverse('lai:automacao_estado'), REMOTE_ADDR='10.0.0.7')
        self.assertFalse(remoto.json()['pode_abrir_pasta'])

    def test_sem_login_nao_acessa(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse('lai:automacao_estado')).status_code, 302)
        self.assertEqual(self.client.post(reverse('lai:automacao_abrir_pasta')).status_code, 302)
