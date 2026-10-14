from django.test import SimpleTestCase
from django.template.loader import render_to_string
from django.urls import reverse

from processos_app.services.diligencia_texto import separar_itens
from processos_app.services import pendencias

from .base import BaseProcessoTestCase


class SepararItensTest(SimpleTestCase):

    def test_uma_providencia_continua_inteira(self):
        texto = 'Regularizar assinatura dos fiscais às fs. 22.043 a 22.080'
        self.assertEqual(separar_itens(texto), [texto])

    def test_frase_depois_da_folha_nao_abre_item(self):
        texto = 'Consta à fl. 21. Regularizar a assinatura do fiscal.'
        self.assertEqual(separar_itens(texto), [texto])

    def test_folha_com_ponto_nao_vira_item(self):
        texto = 'Regularizar atesto por 2 servidores à fl. 21.'
        self.assertEqual(separar_itens(texto), [texto])

    def test_ponto_e_virgula_de_folhas_nao_separa(self):
        casos = [
            'Regularizar assinaturas às fls. 30, 32 a 38; 68, 75 a 84.',
            'Regularizar assinaturas às fls. 36, 38 A 44; 60 A 69.',
            'Regularizar assinaturas às fls. 28, 30 a 36; 55 a 64.',
            'Regularizar assinaturas às fls. 15, 27 a 33, 45 a 54.',
        ]
        for texto in casos:
            with self.subTest(texto=texto):
                self.assertEqual(separar_itens(texto), [texto])

    def test_intervalo_com_traco_nao_vira_marcador(self):
        texto = 'Regularizar assinaturas às fls. 15-27 e 45-54.'
        self.assertEqual(separar_itens(texto), [texto])

    def test_numeracao_com_traco(self):
        texto = (
            '1- Anexar aos autos tombamento; '
            '2- Regularizar assinatura às fls. 233, 234, 235 e 239.'
        )
        self.assertEqual(separar_itens(texto), [
            'Anexar aos autos tombamento',
            'Regularizar assinatura às fls. 233, 234, 235 e 239.',
        ])

    def test_numeracao_com_parenteses_preserva_folhas_do_primeiro_item(self):
        texto = (
            '1) Regularizar assinaturas às fls. 23 a 32; 52 a 63. '
            '2) Regularizar autuação às fls. 23 e 24.'
        )
        self.assertEqual(separar_itens(texto), [
            'Regularizar assinaturas às fls. 23 a 32; 52 a 63.',
            'Regularizar autuação às fls. 23 e 24.',
        ])

    def test_paragrafo_de_recomendacao_fica_um_item(self):
        texto = (
            'Ademais, recomendamos o encaminhamento dos autos à Secretaria '
            'requisitante, para ciência e adoção das providências cabíveis, '
            'especialmente quanto à orientação de que, nos próximos processos, '
            'a abertura seja realizada de forma eletrônica, em observância ao '
            'procedimento atualmente adotado.'
        )
        self.assertEqual(separar_itens(texto), [texto])

    def test_ponto_e_virgula_entre_providencias(self):
        texto = 'Anexar aos autos o tombamento; Regularizar a assinatura do fiscal.'
        self.assertEqual(separar_itens(texto), [
            'Anexar aos autos o tombamento',
            'Regularizar a assinatura do fiscal.',
        ])

    def test_quebras_de_linha_e_continuacao_de_folha(self):
        texto = (
            'Regularizar assinaturas às fls. 30,\n'
            '32 a 38\n'
            'Anexar o tombamento.'
        )
        self.assertEqual(separar_itens(texto), [
            'Regularizar assinaturas às fls. 30, 32 a 38',
            'Anexar o tombamento.',
        ])

    def test_vazio(self):
        self.assertEqual(separar_itens('   '), [])
        self.assertEqual(separar_itens(None), [])


class ChecklistNaFilaTest(BaseProcessoTestCase):

    def test_fila_guarda_o_texto_e_o_checklist_para_abrir(self):
        processo = self.processo_em_analise()
        texto = (
            '1- Anexar aos autos tombamento; '
            '2- Regularizar assinatura às fls. 233, 234, 235 e 239.')
        criada = pendencias.criar(processo.id, self.analista_lic, texto)
        self.client.force_login(self.gestao)
        pagina = self.client.get(reverse('gestao_diligencias'))
        self.assertContains(pagina, texto)
        self.assertContains(pagina, 'data-checklist-ver="%s"' % criada.id)
        self.assertContains(pagina, 'Anexar aos autos tombamento')
        self.assertContains(pagina, '233, 234, 235 e 239')
        self.assertContains(pagina, 'Indicar atendimento')

    def test_indicar_grava_os_itens_marcados(self):
        processo = self.processo_em_analise()
        criada = pendencias.criar(
            processo.id, self.analista_lic,
            '1- Anexar aos autos tombamento; '
            '2- Regularizar assinatura às fls. 233, 234, 235 e 239.')
        self.client.force_login(self.gestao)
        resposta = self.client.post(
            reverse('pend_indicar_atendimento', args=[criada.id]),
            {'itens_concluidos': ['Anexar aos autos tombamento', 'texto fora da lista']})
        self.assertEqual(resposta.status_code, 302)
        criada.refresh_from_db()
        self.assertEqual(criada.status, 'ATENDIMENTO_INDICADO')
        self.assertEqual(criada.itens_concluidos, ['Anexar aos autos tombamento'])


class ChecklistTemplateTest(SimpleTestCase):

    def test_include_renderiza_os_itens(self):
        html = render_to_string('includes/checklist_diligencia.html', {
            'texto': '1) Juntar certidão. 2) Corrigir a autuação.',
        })
        self.assertIn('Juntar certidão.', html)
        self.assertIn('Corrigir a autuação.', html)
        self.assertEqual(html.count('dil-check__item'), 2)
