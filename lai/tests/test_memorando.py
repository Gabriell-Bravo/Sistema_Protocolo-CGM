"""Memorando de reiteração em .docx a partir do modelo da Controladoria."""
import html
import io
import re
import zipfile
from datetime import date

from django.test import SimpleTestCase
from django.urls import reverse

from lai import memorando_docx
from lai.models import MemorandoFalabr, ManifestacaoFalabr
from lai.tests.test_extensao import NUP, _Base


def _texto_do_docx(conteudo):
    with zipfile.ZipFile(io.BytesIO(conteudo)) as z:
        xml = z.read('word/document.xml').decode('utf-8')
    paragrafos = re.findall(r'<w:p[ >].*?</w:p>', xml, flags=re.S)
    return '\n'.join(''.join(re.findall(r'<w:t(?: [^>]*)?>(.*?)</w:t>', p, flags=re.S)) for p in paragrafos)


def _gerar(**extra):
    dados = dict(numero=311, data=date(2026, 11, 4), nup='03996.2026.000970-12',
                 secretaria='Secretaria Municipal de Obras', prazo=date(2026, 11, 12),
                 tratamento='secretario', observacao='ambos')
    dados.update(extra)
    return memorando_docx.gerar(**dados)


class GerarDocxTest(SimpleTestCase):
    def test_troca_todos_os_campos_do_modelo(self):
        texto = _texto_do_docx(_gerar())
        self.assertNotIn('{{', texto)
        self.assertIn('Saquarema, 4 de novembro de 2026.', texto)
        self.assertIn('MEMORANDO 311/2026/CGM', texto)
        self.assertIn('RECEBIDOS AO MEMORANDO 311/2026/CGM', texto)
        self.assertIn('Para: Secretaria Municipal de Obras;', texto)
        self.assertIn('Assunto: Lei de Acesso à Informação – Protocolo nº 03996.2026.000970-12.', texto)
        self.assertIn('registrado sob o Protocolo nº 03996.2026.000970-12, em anexo', texto)
        self.assertIn('até o dia 12 de novembro de 2026, considerando prazo vencido e já prorrogado.', texto)
        self.assertIn('Senhor Secretário,', texto)

    def test_nada_do_memorando_original_sobra(self):
        texto = _texto_do_docx(_gerar())
        for velho in ('310/2026', '000966-35', 'Direitos dos Animais', '27 de outubro', '5 de novembro'):
            self.assertNotIn(velho, texto)

    def test_o_resto_do_modelo_fica_igual(self):
        with zipfile.ZipFile(memorando_docx.MODELO) as modelo, zipfile.ZipFile(io.BytesIO(_gerar())) as gerado:
            self.assertEqual(modelo.namelist(), gerado.namelist())
            for nome in modelo.namelist():
                if nome != 'word/document.xml':
                    self.assertEqual(modelo.read(nome), gerado.read(nome), nome)
        texto = _texto_do_docx(_gerar())
        self.assertIn('Sergio Magno Bravo Monteiro', texto)
        self.assertIn('A Lei de Acesso à Informação estabelece como dever dos órgãos públicos', texto)

    def test_tratamento_e_observacao_do_prazo(self):
        texto = _texto_do_docx(_gerar(tratamento='secretaria', observacao='nenhuma'))
        self.assertIn('Senhora Secretária,', texto)
        self.assertIn('até o dia 12 de novembro de 2026.', texto)
        self.assertIn('prazo já prorrogado.', _texto_do_docx(_gerar(observacao='prorrogado')))
        self.assertIn('prazo vencido.', _texto_do_docx(_gerar(observacao='vencido')))

    def test_caracteres_especiais_nao_quebram_o_xml(self):
        conteudo = _gerar(secretaria='Secretaria de Obras & Serviços <Urbanos> "Z"')
        with zipfile.ZipFile(io.BytesIO(conteudo)) as z:
            from xml.dom import minidom
            minidom.parseString(z.read('word/document.xml'))  # levanta erro se o XML estiver quebrado
        self.assertIn('Secretaria de Obras & Serviços <Urbanos> "Z"', html.unescape(_texto_do_docx(conteudo)))

    def test_campos_invalidos_sao_recusados(self):
        for extra in ({'numero': 'x'}, {'numero': 0}, {'numero': 100000}, {'secretaria': '   '},
                      {'secretaria': 'a' * 161}, {'tratamento': 'rei'}, {'observacao': 'qualquer'},
                      {'prazo': '2026-11-12'}, {'nup': ''}):
            with self.subTest(extra=extra):
                with self.assertRaises(memorando_docx.MemorandoError):
                    _gerar(**extra)

    def test_observacao_padrao_e_nome_do_arquivo(self):
        hoje = date(2026, 11, 4)
        self.assertEqual(memorando_docx.observacao_padrao(date(2026, 11, 1), hoje, True), 'ambos')
        self.assertEqual(memorando_docx.observacao_padrao(date(2026, 11, 1), hoje, False), 'vencido')
        self.assertEqual(memorando_docx.observacao_padrao(date(2026, 11, 9), hoje, True), 'prorrogado')
        self.assertEqual(memorando_docx.observacao_padrao(date(2026, 11, 9), hoje, False), 'nenhuma')
        self.assertEqual(memorando_docx.nome_do_arquivo(310, 2026, '03996.2026.000966-35'),
                         'MEMO 310-2026-CGM - REITERA LAI NUP 03996.2026.000966-35.docx')
        self.assertEqual(memorando_docx.nome_do_arquivo(5, 2026, '../x\\03996'), 'MEMO 5-2026-CGM - REITERA LAI NUP ..03996.docx')


class GerarMemorandosViewTest(_Base):
    def _enviar(self, registros, **extra):
        dados = {'data': '2026-11-04', 'pk': [r.pk for r in registros]}
        n = len(registros)
        dados.update({'numero': [str(311 + i) for i in range(n)], 'secretaria': ['Secretaria de Obras'] * n,
                      'tratamento': ['secretario'] * n, 'prazo': ['2026-11-12'] * n, 'observacao': ['nenhuma'] * n})
        dados.update(extra)
        return self.client.post(reverse('lai:memorandos_gerar'), dados)

    def test_um_pedido_baixa_o_docx_e_guarda_o_historico(self):
        registro = self.registro()
        resp = self._enviar([registro])
        self.assertEqual(resp.status_code, 200)
        self.assertIn('wordprocessingml', resp['Content-Type'])
        self.assertIn('MEMO%20311-2026-CGM', resp['Content-Disposition'])
        self.assertIn(f'Protocolo nº {NUP}', _texto_do_docx(resp.content))
        memo = MemorandoFalabr.objects.get()
        self.assertEqual((memo.numero, memo.ano, memo.secretaria, memo.manifestacao), (311, 2026, 'Secretaria de Obras', registro))
        self.assertEqual(memo.usuario, self.usuario)

    def test_varios_pedidos_vem_num_zip(self):
        a = self.registro()
        b = self.registro(nup='03996.2026.000937-90', assunto='Outro')
        resp = self._enviar([a, b])
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/zip')
        with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
            nomes = sorted(z.namelist())
            self.assertEqual(len(nomes), 2)
            self.assertTrue(nomes[0].startswith('MEMO 311-2026-CGM'))
            self.assertIn('03996.2026.000937-90', nomes[1])
        self.assertEqual(MemorandoFalabr.objects.count(), 2)

    def test_erro_em_um_pedido_nao_grava_nada(self):
        a = self.registro()
        b = self.registro(nup='03996.2026.000937-90', assunto='Outro')
        resp = self._enviar([a, b], secretaria=['Secretaria de Obras', ''])
        self.assertEqual(resp.status_code, 400)
        self.assertIn('03996.2026.000937-90', resp.json()['erro'])
        self.assertEqual(MemorandoFalabr.objects.count(), 0)

    def test_numero_repetido_na_mesma_remessa_e_recusado(self):
        a = self.registro()
        b = self.registro(nup='03996.2026.000937-90', assunto='Outro')
        resp = self._enviar([a, b], numero=['311', '311'])
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(MemorandoFalabr.objects.count(), 0)

    def test_dados_incompletos_ou_pedido_inexistente(self):
        a = self.registro()
        self.assertEqual(self._enviar([a], secretaria=[]).status_code, 400)
        self.assertEqual(self._enviar([a], data='').status_code, 400)
        self.assertEqual(self._enviar([a], prazo=['']).status_code, 400)
        self.assertEqual(self._enviar([a], pk=['999999']).status_code, 400)
        self.assertEqual(self.client.post(reverse('lai:memorandos_gerar'), {}).status_code, 400)
        self.assertEqual(self.client.get(reverse('lai:memorandos_gerar')).status_code, 405)
        self.assertEqual(MemorandoFalabr.objects.count(), 0)

    def test_tela_sugere_o_proximo_numero_e_mostra_o_historico(self):
        registro = self.registro()
        self._enviar([registro], numero=['320'])
        resp = self.client.get(reverse('lai:pendentes'))
        self.assertContains(resp, 'id="lai-memo-inicio"')
        self.assertContains(resp, 'value="321"')
        self.assertContains(resp, 'Memorando 320/2026/CGM para Secretaria de Obras')
        self.assertContains(resp, 'data-secretaria="Secretaria de Obras"')
