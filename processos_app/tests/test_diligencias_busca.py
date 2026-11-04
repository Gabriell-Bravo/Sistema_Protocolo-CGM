"""Busca da tela de diligências: número com ou sem ponto, e no campo origem/pagamento."""
from django.urls import reverse

from processos_app.models import Processo
from processos_app.services import pendencias, tramitacao

from .base import BaseProcessoTestCase


class BuscaDiligenciasTest(BaseProcessoTestCase):
    def _com_diligencia(self, texto, **extra):
        processo = self.novo_processo(**extra)
        tramitacao.assumir(processo.id, self.analista_lic)
        pendencias.criar(processo.id, self.analista_lic, texto)
        return processo

    def _buscar(self, termo):
        self.client.force_login(self.gestao)
        return self.client.get(reverse('gestao_diligencias'), {'termo': termo})

    def test_numero_com_ponto_e_achado_sem_ponto_e_vice_versa(self):
        self._com_diligencia('Falta certidão A', numero_processo='21.361/2023')
        self._com_diligencia('Falta certidão B', numero_processo='9999/2023')
        for termo in ('21361', '21.361', '21361/2023', '21.361/2023', ' 21 361 '):
            with self.subTest(termo=termo):
                resp = self._buscar(termo)
                self.assertContains(resp, 'Falta certidão A')
                self.assertNotContains(resp, 'Falta certidão B')
        gravado_sem_ponto = self._com_diligencia('Falta certidão C', numero_processo='55555/2024')
        self.assertEqual(gravado_sem_ponto.numero_processo, '55555/2024')
        self.assertContains(self._buscar('55.555'), 'Falta certidão C')

    def test_busca_tambem_olha_o_numero_de_origem_pagamento(self):
        processo = self._com_diligencia('Falta certidão D', numero_processo='7777/2026')
        Processo.objects.filter(id=processo.id).update(processo_pagamento='21.361/2023')
        resp = self._buscar('21361')
        self.assertContains(resp, 'Falta certidão D')
        self.assertContains(resp, 'Origem/pagamento: 21.361/2023')

    def test_busca_por_texto_continua_funcionando(self):
        self._com_diligencia('Anexar certidão de débitos', numero_processo='1/2026')
        self.assertContains(self._buscar('certidão de débitos'), 'Anexar certidão de débitos')
        self.assertNotContains(self._buscar('inexistente'), 'Anexar certidão de débitos')


class AvisoDeOcultasTest(BaseProcessoTestCase):
    def test_gestao_e_avisada_de_diligencia_que_a_lista_nao_mostra(self):
        processo = self.novo_processo(numero_processo='3/2026')
        tramitacao.assumir(processo.id, self.analista_lic)
        pendencias.criar(processo.id, self.analista_lic, 'Diligência da Contabilidade')
        Processo.objects.filter(id=processo.id).update(genero='CONTABILIDADE')
        self.client.force_login(self.gestao)
        resp = self.client.get(reverse('gestao_diligencias'))
        self.assertNotContains(resp, 'Diligência da Contabilidade')
        self.assertContains(resp, '1 diligência desta aba não aparece aqui')

    def test_sem_ocultas_nao_mostra_aviso(self):
        processo = self.novo_processo(numero_processo='4/2026')
        tramitacao.assumir(processo.id, self.analista_lic)
        pendencias.criar(processo.id, self.analista_lic, 'Diligência normal')
        self.client.force_login(self.gestao)
        resp = self.client.get(reverse('gestao_diligencias'))
        self.assertContains(resp, 'Diligência normal')
        self.assertNotContains(resp, 'não aparece')
