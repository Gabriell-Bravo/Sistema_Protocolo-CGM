from django.urls import reverse

from processos_app.models import EspecieProcesso, UnidadeAdministrativa
from processos_app.services import permissions as perm
from processos_app.services import secretaria_cgm as svc_cgm
from processos_app.services import tramitacao

from .base import BaseProcessoTestCase


class ProcessosCgmTest(BaseProcessoTestCase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.unidade_cgm, _ = UnidadeAdministrativa.objects.get_or_create(
            nome=svc_cgm.SECRETARIA_CGM,
            defaults={'sigla': 'CGM', 'ativo': True, 'ordem': 5})
        cls.especie_contab, _ = EspecieProcesso.objects.get_or_create(
            nome=svc_cgm.ESPECIE_CONTABILIDADE,
            grupo=svc_cgm.GRUPO_CONTABILIDADE,
            defaults={'ativo': True, 'ordem': 10})

    def test_secretaria_cgm_existe_no_cadastro(self):
        self.assertTrue(
            UnidadeAdministrativa.objects.filter(
                nome=svc_cgm.SECRETARIA_CGM, ativo=True).exists())

    def test_especie_contabilidade_existe(self):
        self.assertTrue(
            EspecieProcesso.objects.filter(
                nome=svc_cgm.ESPECIE_CONTABILIDADE,
                grupo=svc_cgm.GRUPO_CONTABILIDADE,
                ativo=True).exists())

    def test_processo_cgm_nao_aparece_na_lista_comum(self):
        comum = self.novo_processo(numero_processo='cgm-1/2026')
        cgm = self.novo_processo(
            numero_processo='cgm-2/2026',
            secretaria=svc_cgm.SECRETARIA_CGM)

        self.client.force_login(self.protocolo)
        pagina = self.client.get(reverse('listar_processos'))
        self.assertContains(pagina, 'cgm-1/2026')
        self.assertNotContains(pagina, 'cgm-2/2026')
        self.assertContains(pagina, 'Processos CGM')

        aba = self.client.get(reverse('listar_processos') + '?aba=cgm')
        self.assertContains(aba, 'cgm-2/2026')
        self.assertNotContains(aba, 'cgm-1/2026')
        self.assertContains(aba, 'Processos CGM')

    def test_contabilidade_vai_para_aba_cgm_nao_para_analistas(self):
        comum = self.novo_processo(numero_processo='cont-1/2026')
        contab = self.novo_processo(
            self.especie_contab,
            numero_processo='cont-2/2026')

        self.assertEqual(contab.genero, svc_cgm.GRUPO_CONTABILIDADE)
        self.assertTrue(svc_cgm.eh_contabilidade(contab))
        self.assertTrue(svc_cgm.processo_e_da_cgm(contab))
        self.assertFalse(perm.pode_assumir_processo(self.analista_liq, contab))
        self.assertFalse(perm.pode_consultar_processo(self.analista_liq, contab))
        self.assertFalse(perm.pode_assumir_processo(self.analista_lic, contab))

        self.client.force_login(self.protocolo)
        pagina = self.client.get(reverse('listar_processos'))
        self.assertContains(pagina, 'cont-1/2026')
        self.assertNotContains(pagina, 'cont-2/2026')

        aba = self.client.get(reverse('listar_processos') + '?aba=cgm')
        self.assertContains(aba, 'cont-2/2026')
        self.assertNotContains(aba, 'cont-1/2026')

        self.client.force_login(self.analista_liq)
        fila = self.client.get(reverse('area_analista'))
        self.assertEqual(fila.status_code, 200)
        self.assertNotContains(fila, 'cont-2/2026')

    def test_analista_nao_ve_processo_cgm_na_fila_nem_assume(self):
        cgm = self.novo_processo(
            self.especie_liq,
            numero_processo='cgm-3/2026',
            secretaria=svc_cgm.SECRETARIA_CGM)
        self.assertTrue(svc_cgm.processo_e_da_cgm(cgm))
        self.assertFalse(perm.pode_assumir_processo(self.analista_liq, cgm))
        self.assertFalse(perm.pode_consultar_processo(self.analista_liq, cgm))

        self.client.force_login(self.analista_liq)
        fila = self.client.get(reverse('area_analista'))
        self.assertEqual(fila.status_code, 200)
        self.assertNotContains(fila, 'cgm-3/2026')

        aba = self.client.get(reverse('listar_processos') + '?aba=cgm')
        self.assertEqual(aba.status_code, 403)

    def test_gestao_ve_aba_cgm(self):
        cgm = self.novo_processo(
            numero_processo='cgm-4/2026',
            secretaria=svc_cgm.SECRETARIA_CGM)
        contab = self.novo_processo(
            self.especie_contab,
            numero_processo='cont-3/2026')
        self.client.force_login(self.gestao)
        aba = self.client.get(reverse('listar_processos') + '?aba=cgm')
        self.assertEqual(aba.status_code, 200)
        self.assertContains(aba, 'cgm-4/2026')
        self.assertContains(aba, 'cont-3/2026')
        self.assertTrue(perm.pode_consultar_processo(self.gestao, cgm))
        self.assertTrue(perm.pode_consultar_processo(self.gestao, contab))
